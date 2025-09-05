from git import DiffIndex, Repo, Commit

from rag.code_indexer import reindex_files


PROJECT_SUBMODULES_FILE_NAME = "project_submodules.txt"


def switch_submodules_to_branch(repo_dir: str, new_branch_name: str) -> set[str]:
    """Switch all submodules to the specified branch if it exists."""
    try:
        with open(repo_dir + "/" + PROJECT_SUBMODULES_FILE_NAME, "r") as f:
            submodule_names: list[str] = [
                submodule_name
                for submodule_name in f.read().splitlines()
                if submodule_name.strip()
            ]
    except FileNotFoundError:
        return set()

    changed_files: set[str] = set()
    for submodule_name in submodule_names:
        try:
            repo: Repo = Repo(repo_dir + "/" + submodule_name)
            current_branch: str = repo.active_branch.name

            if new_branch_name == current_branch:
                print(
                    f"Submodule {submodule_name} already on branch {new_branch_name}. Skipping."
                )
                continue

            # Switch main repository
            repo.git.checkout(new_branch_name)

            # Get changed files for submodule
            changed_files |= get_repo_changed_files_for_switch(
                repo, current_branch, new_branch_name, f"{submodule_name}/"
            )
        except Exception as e:
            print(
                f"Warning: Failed to pull repository in submodule {submodule_name}: {e}"
            )
    return changed_files


def get_repo_changed_files_for_switch(
    repo: Repo, old_branch: str, new_branch: str, path_prefix: str = ""
) -> set[str]:
    """Get changed files from main repository between two branches."""
    try:
        old_commit: Commit = repo.commit(old_branch)
        new_commit: Commit = repo.commit(new_branch)
        diff_index: DiffIndex = old_commit.diff(new_commit)
        return {f"{path_prefix}{d.a_path or d.b_path}" for d in diff_index}
    except Exception as e:
        print(f"Warning: Failed to get changed files between branches: {e}")
        return set()


def switch_branch(collection_name: str, repo_dir: str, new_branch_name: str) -> None:
    """
    Switch to a new branch and all submodules, then reindex changed files.

    Args:
        collection_name: Name of the collection to reindex
        repo_dir: Path to the repository directory
        new_branch_name: Name of the branch to switch to
    """
    repo: Repo = Repo(repo_dir)
    current_branch: str = repo.active_branch.name

    if new_branch_name == current_branch:
        print(f"Already on branch {new_branch_name}. Skipping.")
        return

    # Switch main repository
    repo.git.checkout(new_branch_name)

    # Get all changed files from main repo
    all_changed_files: set[str] = get_repo_changed_files_for_switch(
        repo, current_branch, new_branch_name
    )

    # Switch all submodules to the new branch and get changed files
    all_changed_files |= switch_submodules_to_branch(repo_dir, new_branch_name)

    if not all_changed_files:
        print("No changed files found. Skipping reindexing.")
        return
    print(f"Changed files: {all_changed_files}")

    # Reindex the changed files
    reindex_files(collection_name, all_changed_files, repo_dir)


def pull_repository(repo: Repo, path_prefix: str) -> tuple[Commit, Commit, str]:
    """Pull repository and return old and new remote commits."""
    remote_name: str = repo.remotes[0].name
    current_branch: str = repo.active_branch.name

    old_remote_commit: Commit = repo.remotes[remote_name].refs[current_branch].commit
    repo.git.pull("--all", "--prune")
    new_remote_commit: Commit = repo.remotes[remote_name].refs[current_branch].commit

    return old_remote_commit, new_remote_commit, path_prefix


def get_changed_files(
    old_commit: Commit, new_commit: Commit, path_prefix: str = ""
) -> set[str]:
    """Get changed files from main repository between two commits."""
    diff_index: DiffIndex = old_commit.diff(new_commit)
    return {f"{path_prefix}{d.a_path or d.b_path}" for d in diff_index}


def pull_submodules(repo_dir: str) -> list[tuple[Commit, Commit, str]]:
    """Pull all submodules in the repository."""
    try:
        with open(repo_dir + "/" + PROJECT_SUBMODULES_FILE_NAME, "r") as f:
            submodule_names: list[str] = [
                submodule_name
                for submodule_name in f.read().splitlines()
                if submodule_name.strip()
            ]
    except FileNotFoundError:
        return []

    old_new_commits: list[tuple[Commit, Commit, str]] = []
    for submodule_name in submodule_names:
        try:
            repo: Repo = Repo(repo_dir + "/" + submodule_name)
            old_new_commits.append(pull_repository(repo, f"{submodule_name}/"))
        except Exception as e:
            print(
                f"Warning: Failed to pull repository in submodule {submodule_name}: {e}"
            )
    return old_new_commits


def pull_current_branch(collection_name: str, repo_dir: str) -> None:
    """
    Pull the current branch and all submodules, then reindex changed files.

    Args:
        collection_name: Name of the collection to reindex
        repo_dir: Path to the repository directory
    """
    repo: Repo = Repo(repo_dir)

    # Pull main repository and get changed commits
    old_new_commits: list[tuple[Commit, Commit, str]] = [pull_repository(repo, "")]

    # Pull all submodules
    old_new_commits.extend(pull_submodules(repo_dir))

    # Get all changed files from main repo and submodules
    all_changed_files: set[str] = set()
    for old_remote_commit, new_remote_commit, path_prefix in old_new_commits:
        all_changed_files |= get_changed_files(
            old_remote_commit, new_remote_commit, path_prefix
        )

    if not all_changed_files:
        print("No changes detected in the repository.")
        return
    else:
        print(f"Changed files: {all_changed_files}")

    # Reindex the changed files
    reindex_files(collection_name, all_changed_files, repo_dir)


def get_current_branch(repo_dir: str) -> str | None:
    """
    Get the name of the current Git branch.

    Args:
        repo_dir: Path to the Git repository

    Returns:
        str: Name of the current branch, or None if not in a Git repository or in detached HEAD state
    """
    try:
        repo = Repo(repo_dir)
        # adding main repo branch name
        branches_names: list[str] = ["Main repo: " + repo.active_branch.name]

        # adding submodules branch names
        try:
            # reading submodules directories names
            with open(repo_dir + "/" + PROJECT_SUBMODULES_FILE_NAME, "r") as f:
                submodule_names: list[str] = [
                    submodule_name
                    for submodule_name in f.read().splitlines()
                    if submodule_name.strip()
                ]
        except FileNotFoundError:
            pass
        else:
            for submodule_name in submodule_names:
                submodule_repo = Repo(repo_dir + "/" + submodule_name)
                branches_names.append(
                    submodule_name + ": " + submodule_repo.active_branch.name
                )

        return "\n".join(branches_names)
    except (ValueError, TypeError):
        # Handle case when in detached HEAD state
        return None
    except Exception:
        # Handle case when not a Git repository
        return None


def get_all_branches(repo_dir: str) -> list[str]:
    """
    Get a list of all available branches in the repository.
    Args:
        repo_dir: Path to the Git repository
    Returns:
        list[str]: A list of branch names (both local and remote, without remote prefixes)
    """
    try:
        repo = Repo(
            repo_dir
        )  # Try to fetch latest remote information and prune deleted branches

        try:
            repo.git.fetch("--all", "--prune")
        except Exception as fetch_error:
            # Continue without fetching if there are network issues or auth problems
            # This ensures we can still list locally known branches
            print(f"Error fetching remote branches: {fetch_error}")

        branches = set()

        # Get local branches
        local_branches = [str(branch) for branch in repo.branches]
        branches.update(local_branches)

        # Get remote branches and remove the remote prefix (e.g., 'origin/')
        for remote in repo.remotes:
            remote_name = remote.name  # e.g., 'origin'
            for ref in remote.refs:
                # Skip HEAD references (e.g., 'origin/HEAD')
                if ref.name.endswith("/HEAD"):
                    continue

                # Remove the remote prefix (e.g., 'origin/feature/auth' -> 'feature/auth')
                branch_name = ref.name[
                    len(remote_name) + 1 :
                ]  # +1 for the '/' separator
                branches.add(branch_name)

        # Convert to sorted list, filtering out any empty strings or HEAD references
        all_branches = [b for b in branches if b and b != "HEAD"]
        return sorted(all_branches)

    except Exception:
        # Handle case when not a Git repository or other errors
        # Could optionally log the error: print(f"Error accessing repository: {e}")
        return []
