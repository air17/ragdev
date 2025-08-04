from git import DiffIndex, Diff, Repo

from rag.code_indexer import reindex_files


def switch_branch(collection_name: str, repo_dir: str, new_branch_name: str) -> None:
    repo = Repo(repo_dir)
    current_branch: str = repo.active_branch.name
    if new_branch_name == current_branch:
        return

    repo.git.checkout(new_branch_name)

    files_diff: DiffIndex[Diff] = repo.commit(new_branch_name).diff(current_branch)
    changed_files: set[str] = set()
    for diff in files_diff:
        blob = diff.a_blob or diff.b_blob
        if blob and blob.path:
            changed_files.add(blob.path)

    if not changed_files:
        return

    reindex_files(collection_name, changed_files, repo_dir)


def fetch_current_branch(collection_name: str, repo_dir: str) -> None:
    repo = Repo(repo_dir)
    remote_name: str = repo.remotes[0].name

    repo.git.fetch("--all", "--prune")

    current_branch: str = repo.active_branch.name
    remote_ref: str = repo.remotes[remote_name].refs[current_branch].name

    diff_index = repo.commit(current_branch).diff(remote_ref)
    changed_files: set[str] = {d.a_path or d.b_path for d in diff_index}

    repo.git.branch("--set-upstream-to", remote_ref, current_branch)

    reindex_files(collection_name, changed_files, repo_dir)


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
        return repo.active_branch.name
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
