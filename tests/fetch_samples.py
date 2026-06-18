"""Kaggle公式サンプルエージェント自動取得スクリプト

Kaggle API を利用して、公式のサンプルエージェント（デッキ・ソースコード等）を自動的にダウンロードし、
`agents_draft/` ディレクトリ配下に展開します。
"""

import os
import sys
import shutil
import zipfile
import tarfile
from pathlib import Path

# プロジェクトルートを sys.path に追加
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def print_auth_guidance(error_msg: str) -> None:
    """Kaggle API 認証エラー時の案内を表示する。"""
    print("\n" + "!" * 60)
    print(" Kaggle API Authentication Error")
    print("!" * 60)
    print(f"Error details: {error_msg}")
    print("\nKaggle API の認証キーが見つからないか、エラーが発生しました。")
    print("以下の手順に従って認証設定を行ってください：\n")
    print("1. Kaggle にログインし、右上のユーザーアイコンから「Settings」を開きます。")
    print("2. 「API」セクションにある「Create New Token」をクリックします。")
    print("3. ダウンロードされた `kaggle.json` ファイルを以下の場所に配置します：")
    print("   - Linux/macOS/Docker:  ~/.kaggle/kaggle.json")
    print("   - Windows:             C:\\Users\\<ユーザー名>\\.kaggle\\kaggle.json")
    print("4. ファイルのパーミッションを変更し、自分だけが読み取れるようにします (Linux/macOS)：")
    print("   chmod 600 ~/.kaggle/kaggle.json")
    print("5. Docker 内で実行する場合は、コンテナ起動時に ~/.kaggle をマウントしているか確認してください：")
    print("   docker run -v ~/.kaggle:/root/.kaggle:ro ...")
    print("!" * 60 + "\n")


def fetch_samples() -> None:
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        print("`kaggle` package is not installed. Attempting to install it dynamically...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "kaggle"])
            # sys.path にユーザーの site-packages を含める
            import site
            user_site = site.getusersitepackages()
            if user_site not in sys.path:
                sys.path.insert(0, user_site)
            from kaggle.api.kaggle_api_extended import KaggleApi
            print("Successfully installed `kaggle` package.")
        except Exception as install_err:
            print(f"Failed to install `kaggle` package automatically: {install_err}")
            print("Please run manually: pip install kaggle")
            sys.exit(1)

    # Kaggle APIの初期化と認証
    print("Initializing Kaggle API client...")
    try:
        api = KaggleApi()
        api.authenticate()
    except Exception as e:
        print_auth_guidance(str(e))
        sys.exit(1)

    # ダウンロード対象のエージェントマッピング
    samples = {
        "sample_lucario": "kiyotah/a-sample-rule-based-agent-mega-lucario-ex-deck",
        "sample_abomasnow": "kiyotah/a-sample-rule-based-agent-mega-abomasnow-ex-deck",
        "sample_dragapult": "kiyotah/a-sample-rule-based-agent-dragapult-ex-deck",
        "sample_iono": "kiyotah/a-sample-rule-based-agent-iono-s-deck",
    }

    draft_dir = project_root / "agents_draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    print(f"Discovered {len(samples)} sample agents to download.")

    for name, kernel_id in samples.items():
        target_dir = draft_dir / name
        print(f"\nFetching {name} from kernel '{kernel_id}'...")

        # 一時的なダウンロード先ディレクトリを作成
        tmp_dir = draft_dir / f"tmp_{name}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # カーネルの Output アーティファクトをダウンロード
            print(f"  Downloading artifacts to {tmp_dir}...")
            api.kernels_output(kernel_id, path=str(tmp_dir))

            # ターゲットディレクトリのクリーンアップと作成
            if target_dir.exists():
                print(f"  Removing existing agent directory: {target_dir}")
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            # ダウンロードされたファイルの展開
            print("  Unpacking downloaded files...")
            for item in tmp_dir.iterdir():
                if item.suffix == ".zip":
                    print(f"    Extracting ZIP archive: {item.name}")
                    with zipfile.ZipFile(item, "r") as zip_ref:
                        zip_ref.extractall(target_dir)
                elif item.suffix in [".gz", ".tgz"] and ".tar" in item.name:
                    print(f"    Extracting Tarball archive: {item.name}")
                    with tarfile.open(item, "r:gz") as tar_ref:
                        tar_ref.extractall(target_dir)
                else:
                    # その他のファイル（main.py や deck.csv など）はそのままコピー
                    print(f"    Copying file: {item.name}")
                    shutil.copy2(item, target_dir / item.name)

            # 最低限必要なファイルがあるか検証
            if not (target_dir / "main.py").exists() or not (target_dir / "deck.csv").exists():
                print(f"  Warning: Expected 'main.py' and 'deck.csv' inside {target_dir}, but they are missing.")
            else:
                print(f"  Successfully fetched: {name} -> {target_dir}")

        except Exception as e:
            print(f"  Error fetching {name}: {e}")
        finally:
            # 一時ディレクトリの削除
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)

    # 同期スクリプト (update_cg.py) を実行して cg ディレクトリを同期
    print("\n" + "=" * 50)
    print(" Running update_cg.py to synchronize simulator files...")
    print("=" * 50)
    try:
        from tests.update_cg import sync_cg_folders
        sync_cg_folders()
    except Exception as e:
        print(f"Error executing update_cg.py: {e}")


if __name__ == "__main__":
    fetch_samples()
