"""
Unit tests for generator.py payload generation and Generator class
"""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Skip compilation tests when optional deps (nuitka/sandboxed) are not installed
try:
    import sandboxed  # noqa: F401
    HAS_COMPILE_DEPS = True
except ImportError:
    HAS_COMPILE_DEPS = False

from osripper.generator import (
    generate_random_string,
    create_bind_payload,
    create_reverse_ssl_tcp_payload,
    create_custom_payload,
    create_btc_miner_payload,
    Generator
)


class TestGenerateRandomString:
    """Tests for generate_random_string function"""
    
    def test_generates_correct_length(self):
        """Test that string is generated with correct length"""
        for length in [5, 10, 15, 20, 50]:
            result = generate_random_string(length)
            assert len(result) == length
    
    def test_generates_only_letters(self):
        """Test that string contains only ASCII letters"""
        result = generate_random_string(100)
        assert result.isalpha()
        assert all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in result)
    
    def test_generates_different_strings(self):
        """Test that multiple calls generate different strings"""
        strings = [generate_random_string(20) for _ in range(10)]
        # All should be unique (very high probability)
        assert len(set(strings)) == len(strings)
    
    def test_zero_length(self):
        """Test edge case of zero length"""
        result = generate_random_string(0)
        assert result == ""


class TestCreateBindPayload:
    """Tests for create_bind_payload function"""
    
    def test_creates_file(self):
        """Test that payload file is created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            result = create_bind_payload(4444, output_path)
            
            assert os.path.exists(output_path)
            assert result == output_path
    
    def test_payload_contains_port(self):
        """Test that payload contains the specified port"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            port = 8888
            create_bind_payload(port, output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            assert f"port = {port}" in content
    
    def test_payload_contains_required_imports(self):
        """Test that payload contains necessary imports"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            create_bind_payload(4444, output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            assert "import zlib" in content
            assert "import base64" in content
            assert "import socket" in content
            assert "import struct" in content
    
    def test_payload_has_main_function(self):
        """Test that payload has a main function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            create_bind_payload(4444, output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            assert "def main():" in content
            assert 'if __name__ == "__main__":' in content


class TestCreateReverseSslTcpPayload:
    """Tests for create_reverse_ssl_tcp_payload function"""
    
    def test_creates_file(self):
        """Test that payload file is created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            result = create_reverse_ssl_tcp_payload("192.168.1.1", 4444, output_path)
            
            assert os.path.exists(output_path)
            assert result == output_path
    
    def test_payload_contains_host_and_port(self):
        """Test that payload contains the specified host and port"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            host = "10.0.0.5"
            port = 9999
            create_reverse_ssl_tcp_payload(host, port, output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            assert f'"{host}"' in content
            assert f" = {port}" in content
    
    def test_payload_contains_ssl_imports(self):
        """Test that payload contains SSL imports"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_payload.py")
            create_reverse_ssl_tcp_payload("192.168.1.1", 4444, output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            # Check that ssl is imported (may be in multi-import statement)
            assert "ssl" in content and "import" in content
            assert "socket" in content and "import" in content
            assert "ssl._create_unverified_context" in content
    
    def test_payload_uses_randomized_variables(self):
        """Test that variable names are randomized"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path1 = os.path.join(tmpdir, "test1.py")
            output_path2 = os.path.join(tmpdir, "test2.py")
            
            create_reverse_ssl_tcp_payload("192.168.1.1", 4444, output_path1)
            create_reverse_ssl_tcp_payload("192.168.1.1", 4444, output_path2)
            
            with open(output_path1, 'r') as f:
                content1 = f.read()
            with open(output_path2, 'r') as f:
                content2 = f.read()
            
            # Variable names should be different (randomized)
            assert content1 != content2


class TestCreateCustomPayload:
    """Tests for create_custom_payload function"""
    
    def test_copies_file_content(self):
        """Test that custom script is copied correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = os.path.join(tmpdir, "source.py")
            output_path = os.path.join(tmpdir, "output.py")
            
            # Create source file
            source_content = "print('Hello World')\n# Custom script"
            with open(source_path, 'w') as f:
                f.write(source_content)
            
            # Copy using function
            result = create_custom_payload(source_path, output_path)
            
            # Verify
            assert os.path.exists(output_path)
            with open(output_path, 'r') as f:
                output_content = f.read()
            
            assert output_content == source_content
            assert result == output_path


class TestCreateBtcMinerPayload:
    """Tests for create_btc_miner_payload function"""
    
    def test_creates_file(self):
        """Test that miner payload file is created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_miner.py")
            btc_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
            result = create_btc_miner_payload(btc_address, output_path)
            
            assert os.path.exists(output_path)
            assert result == output_path
    
    def test_payload_contains_btc_address(self):
        """Test that payload contains the BTC address"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_miner.py")
            btc_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
            create_btc_miner_payload(btc_address, output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            assert btc_address in content
    
    def test_payload_contains_mining_logic(self):
        """Test that payload contains mining-related code"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_miner.py")
            create_btc_miner_payload("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", output_path)
            
            with open(output_path, 'r') as f:
                content = f.read()
            
            assert "import hashlib" in content
            assert "solo.ckpool.org" in content
            assert "mining.subscribe" in content
            assert "def main():" in content


class TestGeneratorClass:
    """Tests for Generator class"""
    
    def test_initialization(self):
        """Test Generator initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            generator = Generator(source_file, "output", quiet=True)
            
            assert generator.source_file == source_file
            assert generator.output_name == "output"
            assert generator.quiet is True
            assert generator.obfuscated is False
            assert generator.compiled is False
    
    def test_create_tmp_workspace(self):
        """Test temporary workspace creation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            generator = Generator(source_file, quiet=True)
            result = generator._create_tmp_workspace()
            
            assert result is True
            assert os.path.exists(generator.tmp_dir)
            
            # Cleanup
            if os.path.exists(generator.tmp_dir):
                shutil.rmtree(generator.tmp_dir)
    
    @patch('osripper.generator.obfuscator')
    def test_obfuscate_success(self, mock_obfuscator):
        """Test successful obfuscation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            # Create expected obfuscated file
            obfuscated_file = os.path.join(tmpdir, "test_or.py")
            
            def mock_main_menu(source, random_suffix=False):
                with open(obfuscated_file, 'w') as f:
                    f.write("obfuscated code")
                return "test_or.py"
            
            mock_obfuscator.MainMenu.side_effect = mock_main_menu
            
            generator = Generator(source_file, quiet=True)
            
            # Change to tmpdir for the test
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = generator.obfuscate()
                
                assert result is True
                assert generator.obfuscated is True
                assert generator.obfuscated_file is not None
            finally:
                os.chdir(original_cwd)
    
    @patch('osripper.generator.obfuscator')
    def test_obfuscate_missing_source(self, mock_obfuscator):
        """Test obfuscation with missing source file"""
        generator = Generator("/nonexistent/file.py", quiet=True)
        result = generator.obfuscate()
        
        assert result is False
        assert generator.obfuscated is False
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed (pip install nuitka sandboxed)")
    @patch('subprocess.run')
    def test_compile_success(self, mock_subprocess):
        """Test successful compilation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            # Mock successful compilation
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_subprocess.return_value = mock_result
            
            generator = Generator(source_file, quiet=True)
            
            # Create a fake binary in the expected location (tmp_dir may not exist yet)
            def create_fake_binary(*args, **kwargs):
                os.makedirs(generator.tmp_dir, exist_ok=True)
                binary_path = os.path.join(generator.tmp_dir, "test.bin")
                with open(binary_path, 'w') as f:
                    f.write("fake binary")
                return mock_result
            
            mock_subprocess.side_effect = create_fake_binary
            
            result = generator.compile()
            
            assert result is True
            assert generator.compiled is True
            
            # Cleanup
            if os.path.exists(generator.tmp_dir):
                shutil.rmtree(generator.tmp_dir)
    
    @pytest.mark.skipif(not HAS_COMPILE_DEPS, reason="nuitka/sandboxed not installed (pip install nuitka sandboxed)")
    @patch('subprocess.run')
    def test_compile_failure(self, mock_subprocess):
        """Test failed compilation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            # Mock failed compilation
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Compilation error"
            mock_subprocess.return_value = mock_result
            
            generator = Generator(source_file, quiet=True)
            result = generator.compile()
            
            assert result is False
            assert generator.compiled is False
            
            # Cleanup
            if os.path.exists(generator.tmp_dir):
                shutil.rmtree(generator.tmp_dir)
    
    def test_cleanup_and_move_results(self):
        """Test cleanup and moving results to results directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            generator = Generator(source_file, "output", quiet=True)
            generator._create_tmp_workspace()
            
            # Create fake obfuscated file
            obfuscated_file = os.path.join(tmpdir, "test_or.py")
            with open(obfuscated_file, 'w') as f:
                f.write("obfuscated")
            generator.obfuscated_file = obfuscated_file
            generator.obfuscated = True
            
            # Change to tmpdir
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = generator.cleanup_and_move_results()
                
                assert result is True
                # results_dir is set to os.path.join(os.getcwd(), "results")
                # so after chdir, it should be in tmpdir/results
                assert os.path.exists(generator.results_dir)
                assert os.path.exists(os.path.join(generator.results_dir, "test_or.py"))
            finally:
                os.chdir(original_cwd)
                # Cleanup
                if os.path.exists(generator.tmp_dir):
                    shutil.rmtree(generator.tmp_dir)
                # Cleanup results directory if created in tmpdir
                results_in_tmpdir = os.path.join(tmpdir, "results")
                if os.path.exists(results_in_tmpdir):
                    shutil.rmtree(results_in_tmpdir)
    
    @patch('osripper.generator.obfuscator')
    def test_generate_obfuscate_only(self, mock_obfuscator):
        """Test generate with obfuscation only"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "test.py")
            with open(source_file, 'w') as f:
                f.write("print('test')")
            
            # Mock obfuscator
            obfuscated_file = os.path.join(tmpdir, "test_or.py")
            
            def mock_main_menu(source, random_suffix=False):
                with open(obfuscated_file, 'w') as f:
                    f.write("obfuscated")
                return "test_or.py"
            
            mock_obfuscator.MainMenu.side_effect = mock_main_menu
            
            generator = Generator(source_file, quiet=True)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = generator.generate(obfuscate=True, compile_binary=False)
                
                # Should succeed with obfuscation
                assert result is True
            finally:
                os.chdir(original_cwd)
                if os.path.exists(generator.tmp_dir):
                    shutil.rmtree(generator.tmp_dir)

