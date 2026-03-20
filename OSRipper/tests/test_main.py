"""
Unit tests for main.py validation and input functions
"""
import pytest
import sys
from unittest.mock import patch, MagicMock
from io import StringIO

# Import functions from main module
from osripper.main import validate_port, validate_ip, get_user_input


class TestValidatePort:
    """Tests for validate_port function"""
    
    def test_valid_port_min_range(self):
        """Test minimum valid port (1024)"""
        assert validate_port("1024") is True
    
    def test_valid_port_max_range(self):
        """Test maximum valid port (65535)"""
        assert validate_port("65535") is True
    
    def test_valid_port_middle_range(self):
        """Test port in middle of valid range"""
        assert validate_port("8080") is True
        assert validate_port("4444") is True
    
    def test_invalid_port_too_low(self):
        """Test port below minimum (< 1024)"""
        assert validate_port("1023") is False
        assert validate_port("80") is False
        assert validate_port("0") is False
    
    def test_invalid_port_too_high(self):
        """Test port above maximum (> 65535)"""
        assert validate_port("65536") is False
        assert validate_port("99999") is False
    
    def test_invalid_port_negative(self):
        """Test negative port numbers"""
        assert validate_port("-1") is False
        assert validate_port("-8080") is False
    
    def test_invalid_port_non_numeric(self):
        """Test non-numeric input"""
        assert validate_port("abc") is False
        assert validate_port("12.34") is False
        assert validate_port("") is False
        assert validate_port("port") is False
    
    def test_invalid_port_special_chars(self):
        """Test special characters"""
        assert validate_port("8080!") is False
        assert validate_port("@8080") is False


class TestValidateIP:
    """Tests for validate_ip function"""
    
    def test_valid_ipv4_addresses(self):
        """Test valid IPv4 addresses"""
        assert validate_ip("192.168.1.1") is True
        assert validate_ip("10.0.0.1") is True
        assert validate_ip("127.0.0.1") is True
        assert validate_ip("0.0.0.0") is True
        assert validate_ip("255.255.255.255") is True
    
    def test_invalid_ip_out_of_range(self):
        """Test IP addresses with octets out of range"""
        assert validate_ip("256.1.1.1") is False
        assert validate_ip("192.168.1.256") is False
        assert validate_ip("999.999.999.999") is False
    
    def test_invalid_ip_wrong_format(self):
        """Test invalid IP format"""
        assert validate_ip("192.168.1") is False
        assert validate_ip("192.168.1.1.1") is False
        assert validate_ip("abc.def.ghi.jkl") is False
        assert validate_ip("") is False
    
    def test_invalid_ip_special_chars(self):
        """Test IP with special characters"""
        assert validate_ip("192.168.1.1!") is False
        assert validate_ip("192-168-1-1") is False
    
    def test_valid_ip_edge_cases(self):
        """Test edge case valid IPs"""
        assert validate_ip("1.1.1.1") is True
        assert validate_ip("8.8.8.8") is True


class TestGetUserInput:
    """Tests for get_user_input function"""
    
    @patch('builtins.input')
    def test_get_user_input_valid_no_validator(self, mock_input):
        """Test getting input without validator"""
        mock_input.return_value = "test input"
        result = get_user_input("Enter something: ")
        assert result == "test input"
        mock_input.assert_called_once()
    
    @patch('builtins.input')
    def test_get_user_input_with_validator_valid(self, mock_input):
        """Test getting input with validator - valid input"""
        mock_input.return_value = "8080"
        result = get_user_input(
            "Enter port: ",
            validator=validate_port,
            error_msg="Invalid port"
        )
        assert result == "8080"
    
    @patch('builtins.input')
    @patch('builtins.print')
    def test_get_user_input_with_validator_retry(self, mock_print, mock_input):
        """Test getting input with validator - retry on invalid"""
        mock_input.side_effect = ["abc", "80", "8080"]
        result = get_user_input(
            "Enter port: ",
            validator=validate_port,
            error_msg="Invalid port"
        )
        assert result == "8080"
        assert mock_input.call_count == 3
        # Should have printed error twice
        assert any("[!] Invalid port" in str(call) for call in mock_print.call_args_list)
    
    @patch('builtins.input')
    def test_get_user_input_strips_whitespace(self, mock_input):
        """Test that input is stripped of whitespace"""
        mock_input.return_value = "  test  "
        result = get_user_input("Enter: ")
        assert result == "test"
    
    @patch('builtins.input')
    def test_get_user_input_empty_retry(self, mock_input):
        """Test that empty input causes retry"""
        mock_input.side_effect = ["", "  ", "valid"]
        result = get_user_input("Enter: ")
        assert result == "valid"
        assert mock_input.call_count == 3
    
    @patch('builtins.input')
    @patch('sys.exit')
    def test_get_user_input_keyboard_interrupt(self, mock_exit, mock_input):
        """Test handling of KeyboardInterrupt"""
        mock_input.side_effect = KeyboardInterrupt()
        mock_exit.side_effect = SystemExit(0)
        
        with pytest.raises(SystemExit):
            get_user_input("Enter: ")
        
        mock_exit.assert_called_once_with(0)
    
    @patch('builtins.input')
    def test_get_user_input_custom_validator(self, mock_input):
        """Test with custom validator function"""
        def is_even(x):
            try:
                return int(x) % 2 == 0
            except:
                return False
        
        mock_input.side_effect = ["3", "5", "8"]
        result = get_user_input("Enter even number: ", validator=is_even)
        assert result == "8"
        assert mock_input.call_count == 3


class TestHelperFunctions:
    """Tests for other helper functions in main.py"""
    
    @patch('os.system')
    def test_clear_screen_posix(self, mock_system):
        """Test clear_screen on POSIX systems"""
        from osripper.main import clear_screen
        with patch('os.name', 'posix'):
            clear_screen()
            mock_system.assert_called_once_with('clear')
    
    @patch('os.system')
    def test_clear_screen_windows(self, mock_system):
        """Test clear_screen on Windows systems"""
        from osripper.main import clear_screen
        with patch('os.name', 'nt'):
            clear_screen()
            mock_system.assert_called_once_with('cls')
    
    def test_display_logo(self):
        """Test that display_logo runs without errors"""
        from osripper.main import display_logo
        # Just ensure it doesn't crash
        display_logo()
    
    def test_display_menu(self):
        """Test that display_menu runs without errors"""
        from osripper.main import display_menu
        # Just ensure it doesn't crash
        display_menu()

