"""Atomic checkpoint persistence under Windows file locks; no model calls."""
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resume_review import ReviewCheckpoint


def windows_lock(code=5):
    error = PermissionError(errno.EACCES, "synthetic Windows file lock")
    error.winerror = code
    return error


class CheckpointWriteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="checkpoint-lock-")
        self.addCleanup(folder.cleanup)
        self.checkpoint = ReviewCheckpoint.__new__(ReviewCheckpoint)
        self.checkpoint.path = Path(folder.name) / "resume_checkpoint.json"
        self.previous = b'{"accepted": {"first": "original"}}\n'
        self.checkpoint.path.write_bytes(self.previous)
        self.checkpoint.data = {"accepted": {"first": "original", "second": "new"}}
        self.pending = self.checkpoint.path.with_suffix(".pending")

    def test_transient_windows_lock_retries_without_truncating_checkpoint(self):
        original_replace = Path.replace
        for code in (5, 32, 33):
            with self.subTest(winerror=code):
                self.checkpoint.path.write_bytes(self.previous)
                attempts = []

                def replace(source, destination):
                    self.assertEqual(destination.read_bytes(), self.previous)
                    self.assertEqual(json.loads(source.read_text()), self.checkpoint.data)
                    attempts.append(source)
                    if len(attempts) < 3:
                        raise windows_lock(code)
                    return original_replace(source, destination)

                with mock.patch.object(Path, "replace", replace), mock.patch("resume_review.time.sleep") as sleep:
                    self.checkpoint.save()
                self.assertEqual(len(attempts), 3)
                self.assertEqual(sleep.call_args_list, [mock.call(0.1), mock.call(0.2)])
                self.assertEqual(json.loads(self.checkpoint.path.read_text()), self.checkpoint.data)
                self.assertFalse(self.pending.exists())

    def test_persistent_lock_preserves_old_checkpoint_and_pending_update(self):
        with mock.patch.object(Path, "replace", side_effect=windows_lock()) as replace, \
                mock.patch("resume_review.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "previous checkpoint is unchanged"):
                self.checkpoint.save()
        self.assertEqual(replace.call_count, 6)
        self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list), 3.1)
        self.assertEqual(self.checkpoint.path.read_bytes(), self.previous)
        self.assertEqual(json.loads(self.pending.read_text()), self.checkpoint.data)

    def test_other_io_errors_fail_immediately_without_losing_checkpoint(self):
        errors = [PermissionError(errno.EACCES, "not a Windows sharing error"),
                  OSError(errno.ENOSPC, "disk full"), windows_lock(1314)]
        for error in errors:
            with self.subTest(error=str(error)), \
                    mock.patch.object(Path, "replace", side_effect=error) as replace, \
                    mock.patch("resume_review.time.sleep") as sleep:
                with self.assertRaises(type(error)):
                    self.checkpoint.save()
                replace.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(self.checkpoint.path.read_bytes(), self.previous)

    @unittest.skipUnless(os.name == "nt", "Windows sharing semantics")
    def test_real_windows_reader_lock_is_retried_after_handle_closes(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        # Allow reading/writing but not deletion/replacement, as another local
        # application's open handle can do. Close only the handle owned here.
        handle = kernel.CreateFileW(str(self.checkpoint.path), 0x80000000, 3, None, 3, 0, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value, ctypes.get_last_error())

        def release(_delay):
            nonlocal handle
            self.assertEqual(self.checkpoint.path.read_bytes(), self.previous)
            self.assertTrue(kernel.CloseHandle(handle))
            handle = None

        try:
            with mock.patch("resume_review.time.sleep", side_effect=release) as sleep:
                self.checkpoint.save()
            sleep.assert_called_once_with(0.1)
        finally:
            if handle is not None:
                kernel.CloseHandle(handle)
        self.assertEqual(json.loads(self.checkpoint.path.read_text()), self.checkpoint.data)
        self.assertFalse(self.pending.exists())


if __name__ == "__main__":
    unittest.main()
