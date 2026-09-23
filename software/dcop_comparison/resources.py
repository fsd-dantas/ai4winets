"""Windows worker isolation with enforced committed-memory and wall-time limits.

The interpreter bootstraps before assignment to the job. The worker waits on stdin
before importing the model or reading its input. Unsupported hosts fail closed.
"""

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import math
import os
from pathlib import Path
import subprocess
import sys
import time


@dataclass(frozen=True)
class Limits:
    wall_seconds: float = 30.0
    memory_bytes: int = 512 * 1024 * 1024
    table_entries: int = 1_000_000

    def __post_init__(self):
        if (type(self.wall_seconds) not in (int, float)
                or not math.isfinite(self.wall_seconds) or self.wall_seconds <= 0):
            raise ValueError('Positive finite wall time required')
        if any(type(v) is not int or v <= 0 for v in (self.memory_bytes, self.table_entries)):
            raise ValueError('Positive integer memory and table budgets required')


class BasicLimits(C.Structure):
    _fields_ = [('PerProcessUserTimeLimit', C.c_int64), ('PerJobUserTimeLimit', C.c_int64),
                ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', C.c_size_t),
                ('MaximumWorkingSetSize', C.c_size_t), ('ActiveProcessLimit', W.DWORD),
                ('Affinity', C.c_size_t), ('PriorityClass', W.DWORD),
                ('SchedulingClass', W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in
                ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class ExtendedLimits(C.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                ('ProcessMemoryLimit', C.c_size_t), ('JobMemoryLimit', C.c_size_t),
                ('PeakProcessMemoryUsed', C.c_size_t), ('PeakJobMemoryUsed', C.c_size_t)]


class Job:
    def __init__(self, memory_bytes):
        if sys.platform != 'win32':
            raise OSError('Enforced comparison workers currently require Windows')
        self.api = C.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([C.c_void_p, W.LPCWSTR], W.HANDLE),
            'SetInformationJobObject': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            'QueryInformationJobObject': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            'AssignProcessToJobObject': ([W.HANDLE, W.HANDLE], W.BOOL),
            'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            'TerminateJobObject': ([W.HANDLE, W.UINT], W.BOOL),
            'CloseHandle': ([W.HANDLE], W.BOOL),
        }
        self.ntdll = C.WinDLL('ntdll')
        self.ntdll.NtResumeProcess.argtypes, self.ntdll.NtResumeProcess.restype = [W.HANDLE], C.c_long
        for name, (args, result) in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        info = ExtendedLimits()
        # PROCESS_MEMORY | KILL_ON_JOB_CLOSE
        info.BasicLimitInformation.LimitFlags = 0x100 | 0x2000
        info.ProcessMemoryLimit = memory_bytes
        if not self.api.SetInformationJobObject(self.handle, 9, C.byref(info), C.sizeof(info)):
            error = C.WinError(C.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, pid):
        """Assign a suspended process, then let it run: nothing it starts escapes the job.

        A venv's python.exe is a launcher that starts the real interpreter as a child. Attaching
        after the launcher runs would race that child out of the job, unlimited and unkillable.
        """
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME
        handle = self.api.OpenProcess(0x100 | 0x1 | 0x800, False, pid)
        if not handle:
            raise C.WinError(C.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, handle):
                raise C.WinError(C.get_last_error())
            if self.ntdll.NtResumeProcess(handle) != 0:
                raise OSError('Could not resume the worker')
        finally:
            self.api.CloseHandle(handle)

    def terminate(self):
        """Kill every process in the job, the launcher's interpreter included."""
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)

    def peak_bytes(self):
        info = ExtendedLimits()
        if not self.api.QueryInformationJobObject(self.handle, 9, C.byref(info), C.sizeof(info), None):
            raise C.WinError(C.get_last_error())
        return info.PeakProcessMemoryUsed

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def supervise(command, limits, *, log_path, env=None):
    """Run a gated child; no unbounded fallback if job setup fails.

    Wall time starts before Popen and ends after child exit (includes imports,
    input validation, solving, evaluation and output serialization). Memory is
    OS-accounted peak commit of any one process in the job, interpreter start-up
    included, not RSS or aggregate memory per agent.
    """
    start = time.perf_counter()
    job, child = None, None
    outcome = 'execution_error'
    error = None
    peak = None
    try:
        job = Job(limits.memory_bytes)
        with Path(log_path).open('wb') as log:
            # CREATE_SUSPENDED (0x4): the child runs only once it is inside the job.
            child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log,
                                     stderr=log, env=env or os.environ.copy(),
                                     creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
            job.attach_and_resume(child.pid)
            remaining = limits.wall_seconds - (time.perf_counter() - start)
            try:
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, limits.wall_seconds)
                child.communicate(b'go\n', timeout=remaining)
                outcome = 'exited'
            except subprocess.TimeoutExpired:
                job.terminate()
                child.communicate()
                outcome = 'time_exceeded'
        peak = job.peak_bytes()
    except OSError as exc:
        error = type(exc).__name__ + ':' + str(getattr(exc, 'winerror', None))
    finally:
        if job is not None:
            job.terminate()
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()
        if job is not None:
            job.close()
    return {'status': outcome, 'error': error,
            'returncode': None if child is None else child.returncode,
            'wall_seconds': time.perf_counter() - start,
            'peak_process_commit_bytes': peak,
            'memory_backend': 'windows-job-process-commit',
            'memory_bootstrap_excluded': False}
