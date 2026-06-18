"""cg フォルダ同期スクリプト

共通の `sample_submission/cg/` ディレクトリ配下のファイルを、
`agents/` 配下のすべてのアクティブなエージェントフォルダへ同期・上書きコピーします。
"""

import os
import shutil
import sys

# プロジェクトルートを sys.path に追加して utils をロード
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.utils import discover_agents


def sync_cg_folders() -> None:
    source_cg_dir = os.path.join(project_root, "sample_submission", "cg")
    if not os.path.exists(source_cg_dir):
        print(f"Error: Source cg directory not found at {source_cg_dir}")
        sys.exit(1)

    print("Discovering active agents...")
    agents = discover_agents(project_root)

    # 同期対象のファイルリストを取得
    files_to_sync = []
    for root, dirs, files in os.walk(source_cg_dir):
        # __pycache__ は同期対象外
        if "__pycache__" in root:
            continue
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, source_cg_dir)
            files_to_sync.append(rel_path)

    print(
        f"Found {len(files_to_sync)} files to synchronize from {source_cg_dir}."
    )

    success_count = 0
    synced_agents = []

    for agent_name, agent_dir in agents.items():
        # sample_submission はコピー元なので同期対象から除外
        if agent_name == "sample_submission":
            continue

        target_cg_dir = os.path.join(agent_dir, "cg")
        print(f"Syncing to agent: {agent_name} -> {target_cg_dir}")

        # ディレクトリがない場合は作成
        os.makedirs(target_cg_dir, exist_ok=True)

        try:
            # 既存のターゲット cg 内の不要なファイルを削除 (クリーンアップ)
            for root, dirs, files in os.walk(target_cg_dir):
                if "__pycache__" in root:
                    continue
                for file in files:
                    full_target_file = os.path.join(root, file)
                    rel_target_file = os.path.relpath(
                        full_target_file, target_cg_dir
                    )
                    if rel_target_file not in files_to_sync:
                        os.remove(full_target_file)
                        print(f"  Removed obsolete file: {rel_target_file}")

            # コピー実行
            for rel_file in files_to_sync:
                src_file = os.path.join(source_cg_dir, rel_file)
                dst_file = os.path.join(target_cg_dir, rel_file)

                # 必要なら親ディレクトリを作成
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)

                shutil.copy2(src_file, dst_file)

            success_count += 1
            synced_agents.append(agent_name)
        except Exception as e:
            print(f"  Error syncing cg folder for {agent_name}: {e}")

    print("\n" + "=" * 50)
    print(" Synchronization Completed")
    print("=" * 50)
    print(f"Successfully synced: {success_count} agents")
    if synced_agents:
        print(f"Agents updated:      {', '.join(synced_agents)}")
    else:
        print("No active agents found in agents/ to update.")
    print("=" * 50)


if __name__ == "__main__":
    sync_cg_folders()
