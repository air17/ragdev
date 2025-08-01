from unittest.mock import patch

from agent_tools.file_list import ls


@patch("os.listdir")
class TestListFiles:
    def test_ls(self, mock_listdir):
        # Setup mock for os.listdir
        mock_listdir.return_value = ["file3.py", "file1.py", "file2.py"]

        # Call the function
        result = ls()

        # Verify result
        assert result == "file1.py\nfile2.py\nfile3.py"

        # Verify os.listdir was called with the correct path
        mock_listdir.assert_called_once_with(".")
