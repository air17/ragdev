from unittest.mock import Mock, patch

import project_management.git_utils as git_utils


def make_diff(a=None, b=None):
    d = Mock()
    d.a_path = a
    d.b_path = b
    return d


def test_get_current_branch_success():
    repo_mock = Mock()
    active_branch = Mock()
    active_branch.name = "main"
    repo_mock.active_branch = active_branch

    with patch("project_management.git_utils.Repo", return_value=repo_mock):
        assert git_utils.get_current_branch("/some/path") == "main"


def test_get_current_branch_error_returns_none():
    with patch(
        "project_management.git_utils.Repo", side_effect=ValueError("not a repo")
    ):
        assert git_utils.get_current_branch("/bad/path") is None


def test_get_all_branches_local_and_remote():
    # local branches - __str__ used in code
    b1 = Mock()
    b1.__str__ = Mock(return_value="dev")
    b2 = Mock()
    b2.__str__ = Mock(return_value="feature/x")

    # remote refs: remote.refs is iterated and ref.name is used
    remote_ref1 = Mock()
    remote_ref1.name = "origin/feature/x"
    remote_ref2 = Mock()
    remote_ref2.name = "origin/HEAD"  # should be skipped
    remote_ref3 = Mock()
    remote_ref3.name = "origin/main"

    remote1 = Mock()
    remote1.name = "origin"
    remote1.refs = [remote_ref1, remote_ref2, remote_ref3]

    repo_mock = Mock()
    repo_mock.branches = [b1, b2]
    repo_mock.remotes = [remote1]

    # repo.git.fetch should be called but may raise - we let it pass
    with patch("project_management.git_utils.Repo", return_value=repo_mock):
        branches = git_utils.get_all_branches("/repo")
        # should include local 'dev', 'feature/x' and remote 'feature/x' and 'main' (unique)
        assert set(branches) == {"dev", "feature/x", "main"}


def test_get_all_branches_repo_error_returns_empty():
    with patch("project_management.git_utils.Repo", side_effect=Exception("boom")):
        assert git_utils.get_all_branches("/no/repo") == []


def test_get_main_repo_changed_files():
    old = Mock()
    new = Mock()
    diffs = [make_diff(a="a.txt"), make_diff(b="b.txt")]
    old.diff.return_value = diffs

    changed = git_utils.get_main_repo_changed_files(old, new)
    assert changed == {"a.txt", "b.txt"}


def test_get_submodule_changed_files():
    # Helper class to emulate remotes that are indexable by int and by name (string)
    class FakeRemotes(list):
        def __init__(self, remotes):
            super().__init__(remotes)
            self._by_name = {r.name: r for r in remotes}

        def __getitem__(self, key):
            if isinstance(key, int):
                return list.__getitem__(self, key)
            return self._by_name[key]

    # prepare submodule objects
    submodule = Mock()
    submodule.name = "sub1"
    submodule.path = "libs/sub1"
    submodule.module_exists.return_value = True

    # sub-repo inside submodule
    sub_repo = Mock()

    # remote object with refs mapping
    remote = Mock()
    remote.name = "origin"
    # ref object to be stored in remote.refs
    ref_main = Mock()
    ref_main.name = "origin/main"
    # remote should support .refs[...] access that returns an object with .commit
    remote.refs = {"main": Mock(commit=Mock())}
    # For iteration, remote.refs is not iterated in this function, so it's fine.

    # set remotes to our FakeRemotes which supports both integer and string indexing
    sub_repo.remotes = FakeRemotes([remote])

    # active branch name
    active_branch = Mock()
    active_branch.name = "main"
    sub_repo.active_branch = active_branch

    # new remote commit (the 'new' commit)
    new_remote_commit = Mock()
    remote.refs["main"].commit = new_remote_commit

    # old remote commit passed in submodule_old_commits
    old_remote_commit = Mock()
    # its diff against new_remote_commit returns diffs
    old_remote_commit.diff.return_value = [
        make_diff(a="file1.py"),
        make_diff(b="file2.py"),
    ]

    # module() should return sub_repo
    submodule.module.return_value = sub_repo

    # repo.submodules is iterable
    repo = Mock()
    repo.submodules = [submodule]

    submodule_old_commits = {"sub1": old_remote_commit}

    changed = git_utils.get_submodule_changed_files(repo, submodule_old_commits)
    assert changed == {"libs/sub1/file1.py", "libs/sub1/file2.py"}


@patch("project_management.git_utils.get_submodule_old_commits_for_switch")
@patch("project_management.git_utils.switch_submodules_to_branch")
@patch("project_management.git_utils.get_main_repo_changed_files_for_switch")
@patch("project_management.git_utils.get_submodule_changed_files_for_switch")
@patch("project_management.git_utils.reindex_files")
def test_switch_branch_noop_when_same_branch(
    mock_reindex,
    mock_sub_changed,
    mock_main_changed,
    mock_switch_subs,
    mock_get_old_commits,
):
    repo_mock = Mock()
    active = Mock()
    active.name = "main"
    repo_mock.active_branch = active

    with patch("project_management.git_utils.Repo", return_value=repo_mock):
        # when new_branch_name equals current branch, function should return early and not call reindex
        git_utils.switch_branch("col", "/repo", "main")
        mock_reindex.assert_not_called()


@patch("project_management.git_utils.get_submodule_old_commits_for_switch")
@patch("project_management.git_utils.switch_submodules_to_branch")
@patch("project_management.git_utils.get_main_repo_changed_files_for_switch")
@patch("project_management.git_utils.get_submodule_changed_files_for_switch")
@patch("project_management.git_utils.reindex_files")
def test_switch_branch_triggers_reindex_when_changes(
    mock_reindex,
    mock_sub_changed,
    mock_main_changed,
    mock_switch_subs,
    mock_get_old_commits,
):
    repo_mock = Mock()
    active = Mock()
    active.name = "dev"
    repo_mock.active_branch = active
    # ensure checkout exists and will be called
    repo_mock.git = Mock()

    mock_get_old_commits.return_value = {"sub1": Mock()}
    # simulate changed files
    mock_main_changed.return_value = {"a.txt"}
    mock_sub_changed.return_value = {"libs/sub1/b.txt"}

    with patch("project_management.git_utils.Repo", return_value=repo_mock):
        git_utils.switch_branch("col", "/repo", "main")
        # checkout on main should have been called
        repo_mock.git.checkout.assert_called_once_with("main")
        # reindex_files called with union of files
        mock_reindex.assert_called_once_with(
            "col", {"a.txt", "libs/sub1/b.txt"}, "/repo"
        )


@patch("project_management.git_utils.get_submodule_old_commits")
@patch("project_management.git_utils.fetch_main_repository")
@patch("project_management.git_utils.fetch_submodules")
@patch("project_management.git_utils.get_main_repo_changed_files")
@patch("project_management.git_utils.get_submodule_changed_files")
@patch("project_management.git_utils.reindex_files")
def test_fetch_current_branch_no_changes(
    mock_reindex,
    mock_sub_changed,
    mock_main_changed,
    mock_fetch_subs,
    mock_fetch_main,
    mock_get_old_commits,
):
    repo_mock = Mock()
    mock_get_old_commits.return_value = {}
    # fetch_main_repository returns old, new commits
    mock_fetch_main.return_value = (Mock(), Mock())
    mock_main_changed.return_value = set()
    mock_sub_changed.return_value = set()

    with patch("project_management.git_utils.Repo", return_value=repo_mock):
        git_utils.fetch_current_branch("col", "/repo")
        mock_reindex.assert_not_called()


@patch("project_management.git_utils.get_submodule_old_commits")
@patch("project_management.git_utils.fetch_main_repository")
@patch("project_management.git_utils.fetch_submodules")
@patch("project_management.git_utils.get_main_repo_changed_files")
@patch("project_management.git_utils.get_submodule_changed_files")
@patch("project_management.git_utils.reindex_files")
def test_fetch_current_branch_with_changes(
    mock_reindex,
    mock_sub_changed,
    mock_main_changed,
    mock_fetch_subs,
    mock_fetch_main,
    mock_get_old_commits,
):
    repo_mock = Mock()
    mock_get_old_commits.return_value = {}

    mock_fetch_main.return_value = (Mock(), Mock())
    mock_main_changed.return_value = {"top.txt"}
    mock_sub_changed.return_value = {"libs/s/x.txt"}

    with patch("project_management.git_utils.Repo", return_value=repo_mock):
        git_utils.fetch_current_branch("col", "/repo")
        mock_reindex.assert_called_once_with(
            "col", {"top.txt", "libs/s/x.txt"}, "/repo"
        )


def test_get_submodule_old_commits_for_switch_no_submodules():
    repo = Mock()
    repo.submodules = []
    assert git_utils.get_submodule_old_commits_for_switch(repo) == {}


def test_get_submodule_old_commits_for_switch_with_valid_submodule():
    # submodule with module that has a valid head and commit
    submodule = Mock()
    submodule.name = "s1"
    submodule.module_exists.return_value = True
    sub_repo = Mock()
    head = Mock()
    head.is_valid.return_value = True
    head.commit = "commit-s1"
    sub_repo.head = head
    submodule.module.return_value = sub_repo

    repo = Mock()
    repo.submodules = [submodule]

    res = git_utils.get_submodule_old_commits_for_switch(repo)
    assert res == {"s1": "commit-s1"}


def test_get_submodule_old_commits_for_switch_handles_exceptions(capfd):
    submodule = Mock()
    submodule.name = "s1"
    # module_exists True but module() raises
    submodule.module_exists.return_value = True
    submodule.module.side_effect = Exception("bad module")

    repo = Mock()
    repo.submodules = [submodule]

    res = git_utils.get_submodule_old_commits_for_switch(repo)
    assert res == {}
    captured = capfd.readouterr()
    assert "Warning: Failed to get current commit for submodule s1" in captured.out


def test_switch_submodules_to_branch_no_submodules():
    repo = Mock()
    repo.submodules = []
    # should not raise
    git_utils.switch_submodules_to_branch(repo, "any-branch")


def test_switch_submodules_to_branch_switches_when_branch_exists():
    submodule = Mock()
    submodule.name = "s1"
    submodule.module_exists.return_value = True
    submodule.module.side_effect = None

    sub_repo = Mock()
    # refs with names like 'origin/main' -> split("/")[-1] yields 'main'
    ref1 = Mock()
    ref1.name = "origin/main"
    sub_repo.refs = [ref1]
    sub_repo.git = Mock()

    submodule.module.return_value = sub_repo

    repo = Mock()
    repo.submodules = [submodule]

    git_utils.switch_submodules_to_branch(repo, "main")
    sub_repo.git.checkout.assert_called_once_with("main")


def test_switch_submodules_to_branch_warns_when_branch_missing(capfd):
    submodule = Mock()
    submodule.name = "s1"
    submodule.module_exists.return_value = True

    sub_repo = Mock()
    ref1 = Mock()
    ref1.name = "origin/other"
    sub_repo.refs = [ref1]
    sub_repo.git = Mock()

    submodule.module.return_value = sub_repo

    repo = Mock()
    repo.submodules = [submodule]

    git_utils.switch_submodules_to_branch(repo, "main")
    captured = capfd.readouterr()
    assert "Warning: Branch main does not exist in submodule s1" in captured.out


def test_get_main_repo_changed_files_for_switch_success():
    repo = Mock()
    old_commit = Mock()
    new_commit = Mock()
    old_commit.diff.return_value = [make_diff(a="a"), make_diff(b="b")]

    # repo.commit should return corresponding commits for names 'old' and 'new'
    repo.commit.side_effect = lambda name: {"old": old_commit, "new": new_commit}[name]

    changed = git_utils.get_main_repo_changed_files_for_switch(repo, "old", "new")
    assert changed == {"a", "b"}


def test_get_main_repo_changed_files_for_switch_handles_exception(capfd):
    repo = Mock()
    repo.commit.side_effect = Exception("no commit")
    changed = git_utils.get_main_repo_changed_files_for_switch(repo, "o", "n")
    assert changed == set()
    captured = capfd.readouterr()
    assert "Warning: Failed to get changed files between branches" in captured.out


def test_get_submodule_changed_files_for_switch_no_submodules():
    repo = Mock()
    repo.submodules = []
    assert git_utils.get_submodule_changed_files_for_switch(repo, {}) == set()


def test_get_submodule_changed_files_for_switch_with_changes():
    submodule = Mock()
    submodule.name = "sub1"
    submodule.path = "libs/sub1"
    submodule.module_exists.return_value = True
    sub_repo = Mock()
    # head valid and has commit
    head = Mock()
    head.is_valid.return_value = True
    new_commit = Mock()
    head.commit = new_commit
    sub_repo.head = head

    submodule.module.return_value = sub_repo

    # old commit that will diff to new_commit
    old_commit = Mock()
    old_commit.diff.return_value = [make_diff(a="f1.py"), make_diff(b="f2.py")]

    repo = Mock()
    repo.submodules = [submodule]

    res = git_utils.get_submodule_changed_files_for_switch(repo, {"sub1": old_commit})
    assert res == {"libs/sub1/f1.py", "libs/sub1/f2.py"}


def test_get_submodule_changed_files_for_switch_handles_exceptions(capfd):
    submodule = Mock()
    submodule.name = "s1"
    submodule.path = "s1path"
    # module_exists True but module() raises
    submodule.module_exists.return_value = True
    submodule.module.side_effect = Exception("boom")

    repo = Mock()
    repo.submodules = [submodule]

    res = git_utils.get_submodule_changed_files_for_switch(repo, {"s1": Mock()})
    assert res == set()
    captured = capfd.readouterr()
    assert "Warning: Failed to get changed files from submodule s1" in captured.out


def test_fetch_main_repository_success():
    # Build a remotes container that supports indexing by name and by index
    class FakeRemotes(list):
        def __init__(self, remotes):
            super().__init__(remotes)
            self._by_name = {r.name: r for r in remotes}

        def __getitem__(self, key):
            if isinstance(key, int):
                return list.__getitem__(self, key)
            return self._by_name[key]

    # remote and refs
    remote = Mock()
    remote.name = "origin"
    # remote.refs[...] should be accessible by name; use dict-like object
    commit_before = Mock()
    commit_after = Mock()
    # make a "refs" object that returns objects with .commit
    refs = {"main": Mock(commit=commit_before)}
    remote.refs = refs

    repo = Mock()
    # remotes must be indexable by int and by name
    repo.remotes = FakeRemotes([remote])
    # active branch
    active = Mock()
    active.name = "main"
    repo.active_branch = active

    # simulate fetch changing the commit object stored under remote.refs['main'].commit
    def do_fetch(*args, **kwargs):
        # mutate the remote.refs to new commit
        remote.refs["main"].commit = commit_after

    repo.git.fetch.side_effect = do_fetch

    old, new = git_utils.fetch_main_repository(repo)
    assert old is commit_before
    assert new is commit_after


def test_get_submodule_old_commits_when_module_exists_and_when_not():
    # Provide a remotes container that supports indexing by int and by name
    class FakeRemotes(list):
        def __init__(self, remotes):
            super().__init__(remotes)
            self._by_name = {r.name: r for r in remotes}

        def __getitem__(self, key):
            if isinstance(key, int):
                return list.__getitem__(self, key)
            return self._by_name[key]

    # submodule that exists and has remotes
    sub1 = Mock()
    sub1.name = "s1"
    sub1.module_exists.return_value = True

    sub_repo1 = Mock()
    remote1 = Mock()
    remote1.name = "origin"
    # remote.refs should support access by branch name and return an object with .commit
    remote1.refs = {"main": Mock(commit="old-commit-s1")}

    # Use FakeRemotes so code can do remotes[0] and remotes['origin']
    sub_repo1.remotes = FakeRemotes([remote1])

    active_branch = Mock()
    active_branch.name = "main"
    sub_repo1.active_branch = active_branch

    sub1.module.return_value = sub_repo1

    # submodule that does not exist -> update called
    sub2 = Mock()
    sub2.name = "s2"
    sub2.module_exists.return_value = False

    repo = Mock()
    repo.submodules = [sub1, sub2]

    res = git_utils.get_submodule_old_commits(repo)
    # should contain entry for s1, and not for s2
    assert res == {"s1": "old-commit-s1"}
    sub2.update.assert_called_once_with(init=True, recursive=True)


def test_fetch_submodules_calls_fetch_and_handles_exceptions(capfd):
    # submodule with module exists and remotes -> fetch should be called
    s1 = Mock()
    s1.name = "s1"
    s1.module_exists.return_value = True
    r1 = Mock()
    r1.name = "origin"
    sub_repo1 = Mock()
    sub_repo1.remotes = [r1]
    sub_repo1.git = Mock()
    s1.module.return_value = sub_repo1

    # submodule that raises on module()
    s2 = Mock()
    s2.name = "s2"
    s2.module_exists.return_value = True
    s2.module.side_effect = Exception("boom")

    repo = Mock()
    repo.submodules = [s1, s2]

    git_utils.fetch_submodules(repo)
    sub_repo1.git.fetch.assert_called_once_with("--prune")
    captured = capfd.readouterr()
    assert "Warning: Failed to fetch submodule s2" in captured.out
