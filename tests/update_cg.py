"""cg フォルダ同期スクリプト

共通の ``sample_submission/cg/`` ディレクトリ配下のファイルを、
3層エージェントディレクトリ構造のすべてのアクティブなエージェントフォルダへ
同期・上書きコピーします。

同期先:
  - ``agents_draft/*/cg/``
  - ``agents/*/cg/``
  - ``latest_submission/cg/``
"""

import os
import shutil
import sys

# プロジェクトルートを算出
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _collect_sync_targets() -> list[tuple[str, str]]:
    """同期対象のエージェントディレクトリを収集する。

    ``discover_agents()`` を使わず、直接ディレクトリ構造をスキャンする。
    ``sample_submission/`` はコピー元なので同期対象に含めない。

    Returns:
        list[tuple[str, str]]: ``(表示名, 絶対パス)`` のリスト。
    """
    targets: list[tuple[str, str]] = []

    # agents_draft/ と agents/ 配下のサブフォルダ
    scan_dirs = [
        ("agents_draft", "draft"),
        ("agents", "completed"),
    ]
    for dir_name, label in scan_dirs:
        parent = os.path.join(project_root, dir_name)
        if not os.path.isdir(parent):
            continue
        for item in sorted(os.listdir(parent)):
            item_path = os.path.join(parent, item)
            if os.path.isdir(item_path):
                targets.append((f"{label}/{item}", item_path))

    # latest_submission/
    submission_dir = os.path.join(project_root, "latest_submission")
    if os.path.isdir(submission_dir):
        targets.append(("latest_submission", submission_dir))

    return targets


def _collect_source_files(source_cg_dir: str) -> list[str]:
    """コピー元の cg ディレクトリ内の同期対象ファイルを相対パスで列挙する。

    ``__pycache__`` 配下は除外する。
    """
    files: list[str] = []
    for root, _dirs, filenames in os.walk(source_cg_dir):
        if "__pycache__" in root:
            continue
        for fname in filenames:
            full_path = os.path.join(root, fname)
            files.append(os.path.relpath(full_path, source_cg_dir))
    return files


def sync_cg_folders() -> None:
    """sample_submission/cg/ を全エージェントフォルダへ同期する。"""
    source_cg_dir = os.path.join(project_root, "sample_submission", "cg")
    if not os.path.isdir(source_cg_dir):
        print(f"Error: Source cg directory not found at {source_cg_dir}")
        sys.exit(1)

    files_to_sync = _collect_source_files(source_cg_dir)
    print(f"Found {len(files_to_sync)} files to synchronize from {source_cg_dir}.")

    targets = _collect_sync_targets()
    if not targets:
        print("No sync targets found.")
        sys.exit(0)

    print(f"Discovered {len(targets)} sync targets.")

    success_count = 0
    synced_agents: list[str] = []

    for agent_name, agent_dir in targets:
        target_cg_dir = os.path.join(agent_dir, "cg")
        print(f"Syncing to: {agent_name} -> {target_cg_dir}")

        os.makedirs(target_cg_dir, exist_ok=True)

        try:
            # 不要ファイルのクリーンアップ
            for root, _dirs, files in os.walk(target_cg_dir):
                if "__pycache__" in root:
                    continue
                for fname in files:
                    full_target = os.path.join(root, fname)
                    rel_target = os.path.relpath(full_target, target_cg_dir)
                    if rel_target not in files_to_sync:
                        os.remove(full_target)
                        print(f"  Removed obsolete file: {rel_target}")

            # ファイルコピー
            for rel_file in files_to_sync:
                src_file = os.path.join(source_cg_dir, rel_file)
                dst_file = os.path.join(target_cg_dir, rel_file)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)

            success_count += 1
            synced_agents.append(agent_name)
        except Exception as e:
            print(f"  Error syncing cg folder for {agent_name}: {e}")

    print("\n" + "=" * 50)
    print(" Synchronization Completed")
    print("=" * 50)
    print(f"Successfully synced: {success_count} targets")
    if synced_agents:
        print(f"Targets updated:     {', '.join(synced_agents)}")
    else:
        print("No targets were updated.")
    print("=" * 50)


if __name__ == "__main__":
    sync_cg_folders()
