# Copyright 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for file parsers."""

import pytest


def test_get_file_type_config():
    """Test that file type configuration is valid."""
    from pipeline.components.parsers import get_file_type_config

    config = get_file_type_config()

    # Check that configuration exists
    assert config is not None
    assert isinstance(config, dict)
    assert len(config) > 0

    # Check that all configs have required keys
    for mime_type, parser_config in config.items():
        assert "parser" in parser_config
        assert "needs_drive" in parser_config
        assert "display_name" in parser_config
        assert callable(parser_config["parser"])
        assert isinstance(parser_config["needs_drive"], bool)
        assert isinstance(parser_config["display_name"], str)


def test_parse_plain_text():
    """Test plain text parsing."""
    from pipeline.components.parsers import parse_plain_text

    content = b"This is a test document.\nIt has multiple lines."
    result = parse_plain_text(content, "test.txt")

    assert result == "This is a test document.\nIt has multiple lines."


def test_parse_plain_text_with_encoding_errors():
    """Test plain text parsing with encoding errors."""
    from pipeline.components.parsers import parse_plain_text

    # Content with invalid UTF-8 bytes
    content = b"Hello \xff World"
    result = parse_plain_text(content, "test.txt")

    # Should handle gracefully (errors='ignore')
    assert "Hello" in result
    assert "World" in result


def test_supported_mime_types():
    """Test that expected MIME types are supported."""
    from pipeline.components.parsers import get_file_type_config

    config = get_file_type_config()

    expected_types = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "text/markdown",
        "image/png",
        "image/jpeg",
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
    ]

    for mime_type in expected_types:
        assert mime_type in config, f"MIME type {mime_type} not supported"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
