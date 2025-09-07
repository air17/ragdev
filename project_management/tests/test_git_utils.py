import pytest
from unittest.mock import Mock, patch
from git import Repo, Commit

# Import the functions to test (adjust import path as needed)
from project_management.git_utils import (
    switch_submodules_to_branch,
    get_repo_changed_files_for_switch,
    switch_branch,
    pull_repository,
    get_changed_files,
    pull_submodules,
    pull_current_branch,
    get_current_branch,
    get_all_branches,
)


class TestSwitchSubmodulesToBranch:
    @patch("project_management.git_utils.Repo")
    @patch("project_management.git_utils.get_repo_changed_files_for_switch")
    def test_switch_submodules_success(self, mock_get_changed_files, mock_repo_class):
        # Arrange
        mock_repo = Mock()
        mock_repo.active_branch.name = "old_branch"
        mock_repo_class.return_value = mock_repo
        mock_get_changed_files.return_value = {"file1.py", "file2.py"}

        # Act
        result = switch_submodules_to_branch(
            "/repo", "new_branch", ("submodule1", "submodule2")
        )

        # Assert
        assert isinstance(result, set)
        mock_repo.git.checkout.assert_called_with("new_branch")
        assert mock_get_changed_files.call_count == 2  # Called for each submodule

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_switch_submodules_no_file(self, mock_open):
        # Act
        result = switch_submodules_to_branch("/repo", "new_branch", ())

        # Assert
        assert result == set()

    @patch("project_management.git_utils.Repo")
    def test_switch_submodules_already_on_branch(self, mock_repo_class, capsys):
        # Arrange
        mock_repo = Mock()
        mock_repo.active_branch.name = "target_branch"
        mock_repo_class.return_value = mock_repo

        # Act
        result = switch_submodules_to_branch("/repo", "target_branch", ("submodule1",))

        # Assert
        captured = capsys.readouterr()
        assert "already on branch" in captured.out.lower()
        assert isinstance(result, set)


class TestGetRepoChangedFilesForSwitch:
    @patch("project_management.git_utils.Repo")
    def test_get_changed_files_success(self, mock_repo_class):
        # Arrange
        mock_repo = Mock()
        mock_old_commit = Mock()
        mock_new_commit = Mock()
        mock_repo.commit.side_effect = [mock_old_commit, mock_new_commit]

        mock_diff_item = Mock()
        mock_diff_item.a_path = "file1.py"
        mock_diff_item.b_path = None
        mock_old_commit.diff.return_value = [mock_diff_item]

        # Act
        result = get_repo_changed_files_for_switch(mock_repo, "old", "new")

        # Assert
        assert result == {"file1.py"}
        mock_old_commit.diff.assert_called_once_with(mock_new_commit)

    def test_get_changed_files_exception(self, capsys):
        # Arrange
        mock_repo = Mock()
        mock_repo.commit.side_effect = Exception("Git error")

        # Act
        result = get_repo_changed_files_for_switch(mock_repo, "old", "new")

        # Assert
        assert result == set()
        captured = capsys.readouterr()
        assert "warning" in captured.out.lower()


class TestSwitchBranch:
    @patch("project_management.git_utils.reindex_files")
    @patch("project_management.git_utils.switch_submodules_to_branch")
    @patch("project_management.git_utils.get_repo_changed_files_for_switch")
    @patch("project_management.git_utils.Repo")
    def test_switch_branch_success(
        self,
        mock_repo_class,
        mock_get_changed_files,
        mock_switch_submodules,
        mock_reindex,
    ):
        # Arrange
        mock_repo = Mock()
        mock_repo.active_branch.name = "old_branch"
        mock_repo_class.return_value = mock_repo
        mock_get_changed_files.return_value = {"file1.py"}
        mock_switch_submodules.return_value = {"file2.py"}

        # Act
        switch_branch("collection", "/repo", "new_branch")

        # Assert
        mock_repo.git.checkout.assert_called_once_with("new_branch")
        mock_reindex.assert_called_once_with(
            "collection", {"file1.py", "file2.py"}, "/repo"
        )

    @patch("project_management.git_utils.Repo")
    def test_switch_branch_already_on_target(self, mock_repo_class, capsys):
        # Arrange
        mock_repo = Mock()
        mock_repo.active_branch.name = "target_branch"
        mock_repo_class.return_value = mock_repo

        # Act
        switch_branch("collection", "/repo", "target_branch")

        # Assert
        captured = capsys.readouterr()
        assert "already on branch" in captured.out.lower()

    @patch("project_management.git_utils.reindex_files")
    @patch("project_management.git_utils.switch_submodules_to_branch")
    @patch("project_management.git_utils.get_repo_changed_files_for_switch")
    @patch("project_management.git_utils.Repo")
    def test_switch_branch_no_changes(
        self,
        mock_repo_class,
        mock_get_changed_files,
        mock_switch_submodules,
        mock_reindex,
        capsys,
    ):
        # Arrange
        mock_repo = Mock()
        mock_repo.active_branch.name = "old_branch"
        mock_repo_class.return_value = mock_repo
        mock_get_changed_files.return_value = set()
        mock_switch_submodules.return_value = set()

        # Act
        switch_branch("collection", "/repo", "new_branch")

        # Assert
        captured = capsys.readouterr()
        assert "no changed files found" in captured.out.lower()
        mock_reindex.assert_not_called()


class TestPullRepository:
    def test_pull_repository_success(self):
        # Arrange
        mock_repo = Mock()

        # Mock the remote access
        mock_remote = Mock()
        mock_remote.name = "origin"

        # Mock repo.remotes to support both [0] and ['origin'] access
        def remotes_getitem(key):
            if key == 0 or key == "origin":
                return mock_remote
            raise KeyError(key)

        mock_repo.remotes.__getitem__ = Mock(side_effect=remotes_getitem)

        # Mock active branch
        mock_repo.active_branch.name = "main"

        # Mock commits - these will be the return values
        old_commit = Mock()
        new_commit = Mock()

        # Mock the refs access chain
        mock_ref = Mock()
        mock_ref.commit = old_commit  # Initially return old commit

        mock_refs = Mock()
        mock_refs.__getitem__ = Mock(return_value=mock_ref)
        mock_remote.refs = mock_refs

        # Mock git pull and change commit after pull
        def mock_pull(*args):
            mock_ref.commit = new_commit  # Change commit after pull

        mock_repo.git = Mock()
        mock_repo.git.pull.side_effect = mock_pull

        # Act
        result = pull_repository(mock_repo, "")

        # Assert
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] == old_commit
        assert result[1] == new_commit
        mock_repo.git.pull.assert_called_once_with("--all", "--prune")


class TestGetChangedFiles:
    def test_get_changed_files_success(self):
        # Arrange
        mock_old_commit = Mock()
        mock_new_commit = Mock()

        mock_diff_item = Mock()
        mock_diff_item.a_path = "file1.py"
        mock_diff_item.b_path = None
        mock_old_commit.diff.return_value = [mock_diff_item]

        # Act
        result = get_changed_files(mock_old_commit, mock_new_commit)

        # Assert
        assert result == {"file1.py"}


class TestPullSubmodules:
    @patch("project_management.git_utils.Repo")
    @patch("project_management.git_utils.pull_repository")
    def test_pull_submodules_success(self, mock_pull_repo, mock_repo_class):
        # Arrange
        mock_pull_repo.return_value = (Mock(), Mock())
        mock_pull_repo.return_value = (Mock(), Mock(), "")  # Added third parameter
        # Act
        result = pull_submodules("/repo", ("submodule1", "submodule2"))

        # Assert
        assert isinstance(result, list)
        assert len(result) == 2
        assert mock_pull_repo.call_count == 2

    def test_pull_submodules_no_file(self):
        # Act
        result = pull_submodules("/repo", ())

        # Assert
        assert result == []


class TestPullCurrentBranch:
    @patch("project_management.git_utils.reindex_files")
    @patch("project_management.git_utils.pull_submodules")
    @patch("project_management.git_utils.pull_repository")
    @patch("project_management.git_utils.get_changed_files")
    @patch("project_management.git_utils.Repo")
    def test_pull_current_branch_with_changes(
        self,
        mock_repo_class,
        mock_get_changed_files,
        mock_pull_repo,
        mock_pull_submodules,
        mock_reindex,
    ):
        # Arrange
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_pull_repo.return_value = (Mock(), Mock())
        mock_pull_repo.return_value = (Mock(), Mock(), "")  # Added third parameter
        mock_pull_submodules.return_value = [
            (Mock(), Mock(), "sub1/")
        ]  # Added third parameter

        # Act
        pull_current_branch("collection", "/repo")

        # Assert
        mock_reindex.assert_called_once()

    @patch("project_management.git_utils.pull_submodules")
    @patch("project_management.git_utils.pull_repository")
    @patch("project_management.git_utils.get_changed_files")
    @patch("project_management.git_utils.Repo")
    def test_pull_current_branch_no_changes(
        self,
        mock_repo_class,
        mock_get_changed_files,
        mock_pull_repo,
        mock_pull_submodules,
        capsys,
    ):
        # Arrange
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_pull_repo.return_value = (Mock(), Mock())
        mock_pull_repo.return_value = (Mock(), Mock(), "")  # Added third parameter
        mock_get_changed_files.return_value = set()

        # Act
        pull_current_branch("collection", "/repo")

        # Assert
        captured = capsys.readouterr()
        assert "no changes detected" in captured.out.lower()


class TestGetCurrentBranch:
    @patch("project_management.git_utils.Repo")
    def test_get_current_branch_with_submodules(self, mock_repo_class):
        # Arrange
        main_repo = Mock()
        main_repo.active_branch.name = "main"

        sub_repo1 = Mock()
        sub_repo1.active_branch.name = "feature1"

        sub_repo2 = Mock()
        sub_repo2.active_branch.name = "feature2"

        mock_repo_class.side_effect = [main_repo, sub_repo1, sub_repo2]

        # Act
        result = get_current_branch("/repo", ("submodule1", "submodule2"))

        # Assert
        assert "Main repo: main" in result
        assert "feature1" in result
        assert "feature2" in result

    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("project_management.git_utils.Repo")
    def test_get_current_branch_no_submodules(self, mock_repo_class, mock_open):
        # Arrange
        mock_repo = Mock()
        mock_repo.active_branch.name = "main"
        mock_repo_class.return_value = mock_repo

        # Act
        result = get_current_branch("/repo")

        # Assert
        assert result == "Main repo: main"

    @patch("project_management.git_utils.Repo", side_effect=Exception("Not a git repo"))
    def test_get_current_branch_not_git_repo(self, mock_repo_class):
        with pytest.raises(Exception):
            get_current_branch("/not-a-repo")

    @patch("project_management.git_utils.Repo", side_effect=ValueError("Detached HEAD"))
    def test_get_current_branch_detached_head(self, mock_repo_class):
        # Assert raises ValueError
        with pytest.raises(ValueError):
            get_current_branch("/repo")


class TestGetAllBranches:
    @patch("project_management.git_utils.Repo")
    def test_get_all_branches_success(self, mock_repo_class):
        # Arrange
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Mock local branches
        mock_branch1 = Mock()
        mock_branch1.__str__ = lambda x: "main"
        mock_branch2 = Mock()
        mock_branch2.__str__ = lambda x: "feature/test"
        mock_repo.branches = [mock_branch1, mock_branch2]

        # Mock remotes
        mock_remote = Mock()
        mock_remote.name = "origin"
        mock_ref1 = Mock()
        mock_ref1.name = "origin/develop"
        mock_ref2 = Mock()
        mock_ref2.name = "origin/HEAD"  # Should be filtered out
        mock_remote.refs = [mock_ref1, mock_ref2]
        mock_repo.remotes = [mock_remote]

        # Act
        result = get_all_branches("/repo")

        # Assert
        assert isinstance(result, list)
        assert "main" in result
        assert "feature/test" in result
        assert "develop" in result
        assert "HEAD" not in result
        mock_repo.git.fetch.assert_called_once_with("--all", "--prune")

    @patch("project_management.git_utils.Repo")
    def test_get_all_branches_fetch_error(self, mock_repo_class, capsys):
        # Arrange
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_repo.git.fetch.side_effect = Exception("Network error")
        mock_repo.branches = []
        mock_repo.remotes = []

        # Act
        result = get_all_branches("/repo")

        # Assert
        assert isinstance(result, list)
        captured = capsys.readouterr()
        assert "error fetching remote branches" in captured.out.lower()

    @patch("project_management.git_utils.Repo", side_effect=Exception("Not a git repo"))
    def test_get_all_branches_not_git_repo(self, mock_repo_class):
        # Act
        result = get_all_branches("/not-a-repo")

        # Assert
        assert result == []


# Fixtures that might be useful for more complex testing
@pytest.fixture
def mock_repo():
    """Fixture providing a mock Git repository."""
    repo = Mock(spec=Repo)
    repo.active_branch.name = "main"
    repo.remotes = []
    repo.branches = []
    return repo


@pytest.fixture
def mock_commit():
    """Fixture providing a mock Git commit."""
    commit = Mock(spec=Commit)
    commit.diff.return_value = []
    return commit


@pytest.fixture
def sample_submodules_file():
    """Fixture providing sample submodules file content."""
    return "submodule1\nsubmodule2\n\n"  # Include empty line to test filtering
