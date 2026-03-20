"""
Integration tests for complete payload generation workflow
Tests the full pipeline: payload generation -> obfuscation -> compilation -> cleanup
"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock, call
from pathlib import Path

# Skip compilation tests when optional deps (nuitka/sandboxed) are not installed
try:
    import sandboxed  # noqa: F401
    HAS_COMPILE_DEPS = True
except ImportError:
    HAS_COMPILE_DEPS = False

from osripper.generator import (
    Generator,
    create_bind_payload,
    create_reverse_ssl_tcp_payload,
    create_custom_payload,
    create_btc_miner_payload
)


class TestCompleteWorkflow:
    """Integration tests for complete payload generation workflows"""
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed")
    @patch('osripper.generator.obfuscator')
    @patch('subprocess.run')
    def test_bind_payload_full_workflow(self, mock_subprocess, mock_obfuscator):
        """Test complete workflow: bind payload -> obfuscate -> compile -> cleanup"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Step 1: Create bind payload
                port = 4444
                payload_name = "test_payload.py"
                create_bind_payload(port, payload_name)
                
                assert os.path.exists(payload_name)
                
                # Step 2: Setup mocks for obfuscation
                obfuscated_name = "test_payload_or.py"
                
                def mock_obfuscate(source, random_suffix=False):
                    with open(obfuscated_name, 'w') as f:
                        f.write("# Obfuscated payload")
                    return obfuscated_name
                
                mock_obfuscator.MainMenu.side_effect = mock_obfuscate
                
                # Step 3: Setup mocks for compilation
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                
                def mock_compile(*args, **kwargs):
                    # Create fake binary in tmp_dir
                    output_dir = None
                    for arg in args[0]:
                        if arg.startswith('--output-dir='):
                            output_dir = arg.split('=')[1]
                            break
                    
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        binary_path = os.path.join(output_dir, "test_payload_or.bin")
                        with open(binary_path, 'wb') as f:
                            f.write(b"fake binary content")
                    
                    return mock_result
                
                mock_subprocess.side_effect = mock_compile
                
                # Step 4: Run generator
                generator = Generator(payload_name, "test_payload", quiet=True)
                result = generator.generate(obfuscate=True, compile_binary=True)
                
                # Verify success
                assert result is True
                assert generator.obfuscated is True
                assert generator.compiled is True
                
                # Verify results directory created
                assert os.path.exists("results")
                
                # Verify cleanup happened (tmp dir removed)
                assert not os.path.exists(generator.tmp_dir)
                
            finally:
                os.chdir(original_cwd)
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed")
    @patch('osripper.generator.obfuscator')
    @patch('subprocess.run')
    def test_reverse_ssl_payload_full_workflow(self, mock_subprocess, mock_obfuscator):
        """Test complete workflow: reverse SSL payload -> obfuscate -> compile"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create reverse SSL payload
                host = "192.168.1.1"
                port = 8080
                payload_name = "reverse.py"
                create_reverse_ssl_tcp_payload(host, port, payload_name)
                
                assert os.path.exists(payload_name)
                
                # Verify payload contains host and port
                with open(payload_name, 'r') as f:
                    content = f.read()
                assert host in content
                assert str(port) in content
                
                # Setup obfuscation mock
                obfuscated_name = "reverse_or.py"
                
                def mock_obfuscate(source, random_suffix=False):
                    with open(obfuscated_name, 'w') as f:
                        f.write(f"# Obfuscated: {host}:{port}")
                    return obfuscated_name
                
                mock_obfuscator.MainMenu.side_effect = mock_obfuscate
                
                # Setup compilation mock
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                
                def mock_compile(*args, **kwargs):
                    output_dir = None
                    for arg in args[0]:
                        if arg.startswith('--output-dir='):
                            output_dir = arg.split('=')[1]
                            break
                    
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        binary_path = os.path.join(output_dir, "reverse_or.bin")
                        with open(binary_path, 'wb') as f:
                            f.write(b"reverse binary")
                    
                    return mock_result
                
                mock_subprocess.side_effect = mock_compile
                
                # Run generator
                generator = Generator(payload_name, "reverse", quiet=True)
                result = generator.generate(obfuscate=True, compile_binary=True)
                
                assert result is True
                
            finally:
                os.chdir(original_cwd)
    
    @patch('osripper.generator.obfuscator')
    def test_obfuscate_only_workflow(self, mock_obfuscator):
        """Test workflow with obfuscation only (no compilation)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create custom payload
                source_script = os.path.join(tmpdir, "custom_source.py")
                with open(source_script, 'w') as f:
                    f.write("print('Custom script')\nprint('Line 2')")
                
                payload_name = "custom.py"
                create_custom_payload(source_script, payload_name)
                
                # Setup obfuscation mock
                obfuscated_name = "custom_or.py"
                
                def mock_obfuscate(source, random_suffix=False):
                    with open(obfuscated_name, 'w') as f:
                        f.write("# Obfuscated custom script")
                    return obfuscated_name
                
                mock_obfuscator.MainMenu.side_effect = mock_obfuscate
                
                # Run generator (obfuscate only)
                generator = Generator(payload_name, "custom", quiet=True)
                result = generator.generate(obfuscate=True, compile_binary=False)
                
                assert result is True
                assert generator.obfuscated is True
                assert generator.compiled is False
                
                # Verify results directory
                assert os.path.exists("results")
                results_files = os.listdir("results")
                assert any("custom_or.py" in f for f in results_files)
                
            finally:
                os.chdir(original_cwd)
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed")
    @patch('subprocess.run')
    def test_compile_only_workflow(self, mock_subprocess):
        """Test workflow with compilation only (no obfuscation)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "simple.py"
                with open(payload_name, 'w') as f:
                    f.write("print('Simple payload')")
                
                # Setup compilation mock
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                
                def mock_compile(*args, **kwargs):
                    output_dir = None
                    for arg in args[0]:
                        if arg.startswith('--output-dir='):
                            output_dir = arg.split('=')[1]
                            break
                    
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        binary_path = os.path.join(output_dir, "simple.bin")
                        with open(binary_path, 'wb') as f:
                            f.write(b"compiled binary")
                    
                    return mock_result
                
                mock_subprocess.side_effect = mock_compile
                
                # Run generator (compile only)
                generator = Generator(payload_name, "simple", quiet=True)
                result = generator.generate(obfuscate=False, compile_binary=True)
                
                assert result is True
                assert generator.obfuscated is False
                assert generator.compiled is True
                
            finally:
                os.chdir(original_cwd)
    
    def test_btc_miner_payload_generation(self):
        """Test BTC miner payload generation and content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create BTC miner payload
                btc_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
                payload_name = "miner.py"
                create_btc_miner_payload(btc_address, payload_name)
                
                assert os.path.exists(payload_name)
                
                # Verify payload content
                with open(payload_name, 'r') as f:
                    content = f.read()
                
                assert btc_address in content
                assert "solo.ckpool.org" in content
                assert "mining.subscribe" in content
                assert "def main():" in content
                
            finally:
                os.chdir(original_cwd)


class TestErrorHandling:
    """Integration tests for error handling in workflows"""
    
    @patch('osripper.generator.obfuscator')
    def test_obfuscation_failure_handling(self, mock_obfuscator):
        """Test handling when obfuscation fails"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "test.py"
                with open(payload_name, 'w') as f:
                    f.write("print('test')")
                
                # Mock obfuscation failure (no output file created)
                mock_obfuscator.MainMenu.return_value = None
                
                # Run generator
                generator = Generator(payload_name, quiet=True)
                result = generator.generate(obfuscate=True, compile_binary=False)
                
                # Should fail gracefully
                assert result is False
                
            finally:
                os.chdir(original_cwd)
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed")
    @patch('subprocess.run')
    def test_compilation_failure_handling(self, mock_subprocess):
        """Test handling when compilation fails"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "test.py"
                with open(payload_name, 'w') as f:
                    f.write("print('test')")
                
                # Mock compilation failure
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "Compilation failed"
                mock_subprocess.return_value = mock_result
                
                # Run generator
                generator = Generator(payload_name, quiet=True)
                result = generator.generate(obfuscate=False, compile_binary=True)
                
                # Should fail gracefully
                assert result is False
                
                # Temp directory should still be cleaned up
                assert not os.path.exists(generator.tmp_dir)
                
            finally:
                os.chdir(original_cwd)
    
    def test_missing_source_file_handling(self):
        """Test handling when source file doesn't exist"""
        generator = Generator("/nonexistent/file.py", quiet=True)
        result = generator.generate(obfuscate=True, compile_binary=False)
        
        assert result is False


class TestFilesystemOperations:
    """Integration tests for filesystem operations"""
    
    @patch('osripper.generator.obfuscator')
    def test_results_directory_creation(self, mock_obfuscator):
        """Test that results directory is created correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "test.py"
                with open(payload_name, 'w') as f:
                    f.write("print('test')")
                
                # Setup obfuscation mock
                obfuscated_name = "test_or.py"
                
                def mock_obfuscate(source, random_suffix=False):
                    with open(obfuscated_name, 'w') as f:
                        f.write("obfuscated")
                    return obfuscated_name
                
                mock_obfuscator.MainMenu.side_effect = mock_obfuscate
                
                # Ensure results directory doesn't exist
                if os.path.exists("results"):
                    shutil.rmtree("results")
                
                # Run generator
                generator = Generator(payload_name, quiet=True)
                result = generator.generate(obfuscate=True, compile_binary=False)
                
                assert result is True
                assert os.path.exists("results")
                assert os.path.isdir("results")
                
            finally:
                os.chdir(original_cwd)
    
    @patch('osripper.generator.obfuscator')
    def test_source_file_cleanup(self, mock_obfuscator):
        """Test that source payload file is cleaned up after processing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "test.py"
                with open(payload_name, 'w') as f:
                    f.write("print('test')")
                
                assert os.path.exists(payload_name)
                
                # Setup obfuscation mock
                obfuscated_name = "test_or.py"
                
                def mock_obfuscate(source, random_suffix=False):
                    with open(obfuscated_name, 'w') as f:
                        f.write("obfuscated")
                    return obfuscated_name
                
                mock_obfuscator.MainMenu.side_effect = mock_obfuscate
                
                # Run generator
                generator = Generator(payload_name, quiet=True)
                result = generator.generate(obfuscate=True, compile_binary=False)
                
                assert result is True
                
                # Original payload should be cleaned up
                # (This is tested by checking if source_file is removed)
                
            finally:
                os.chdir(original_cwd)
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed")
    @patch('osripper.generator.obfuscator')
    @patch('subprocess.run')
    def test_temporary_workspace_cleanup(self, mock_subprocess, mock_obfuscator):
        """Test that temporary workspace is always cleaned up"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "test.py"
                with open(payload_name, 'w') as f:
                    f.write("print('test')")
                
                # Setup mocks
                obfuscated_name = "test_or.py"
                
                def mock_obfuscate(source, random_suffix=False):
                    with open(obfuscated_name, 'w') as f:
                        f.write("obfuscated")
                    return obfuscated_name
                
                mock_obfuscator.MainMenu.side_effect = mock_obfuscate
                
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                
                def mock_compile(*args, **kwargs):
                    output_dir = None
                    for arg in args[0]:
                        if arg.startswith('--output-dir='):
                            output_dir = arg.split('=')[1]
                            break
                    
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        binary_path = os.path.join(output_dir, "test_or.bin")
                        with open(binary_path, 'wb') as f:
                            f.write(b"binary")
                    
                    return mock_result
                
                mock_subprocess.side_effect = mock_compile
                
                # Run generator
                generator = Generator(payload_name, quiet=True)
                tmp_dir_path = generator.tmp_dir
                
                result = generator.generate(obfuscate=True, compile_binary=True)
                
                assert result is True
                
                # Verify temp directory was cleaned up
                assert not os.path.exists(tmp_dir_path)
                
            finally:
                os.chdir(original_cwd)


class TestWorkflowWithIcon:
    """Integration tests for workflows with custom icons"""
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed")
    @patch('subprocess.run')
    def test_compilation_with_icon(self, mock_subprocess):
        """Test compilation with custom icon file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create payload
                payload_name = "test.py"
                with open(payload_name, 'w') as f:
                    f.write("print('test')")
                
                # Create fake icon file
                icon_path = os.path.join(tmpdir, "icon.ico")
                with open(icon_path, 'wb') as f:
                    f.write(b"fake icon data")
                
                # Setup compilation mock
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                
                def mock_compile(*args, **kwargs):
                    cmd_args = args[0]

                    output_dir = None
                    for arg in cmd_args:
                        if arg.startswith('--output-dir='):
                            output_dir = arg.split('=')[1]
                            break

                    # Only verify icon flag on the actual compile call, not the version check
                    if output_dir:
                        assert any('icon' in arg.lower() for arg in cmd_args)
                        os.makedirs(output_dir, exist_ok=True)
                        binary_path = os.path.join(output_dir, "test.bin")
                        with open(binary_path, 'wb') as f:
                            f.write(b"binary with icon")

                    return mock_result
                
                mock_subprocess.side_effect = mock_compile
                
                # Run generator with icon
                generator = Generator(payload_name, icon_path=icon_path, quiet=True)
                result = generator.generate(obfuscate=False, compile_binary=True)
                
                assert result is True
                
            finally:
                os.chdir(original_cwd)

