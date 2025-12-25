import os
import sys
import subprocess
import requests
import qrcode
import base64
import re
import tempfile
from urllib.parse import urlparse

# Configuration
README_PATH = "README.md"
SHORTCUT_PATH = "MessageDict.shortcut"
SECRETS_FILE = ".secrets"
GITHUB_REPO = None  # Will be detected from git remote

def load_secrets():
    """Load secrets from .secrets file or environment variables."""
    token = os.environ.get("GITHUB_TOKEN")
    
    # Try to load from secrets file if not in environment
    if not token and os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('GITHUB_TOKEN='):
                        token = line.split('=', 1)[1].strip()
                        if token:
                            break
        except Exception as e:
            print(f"⚠️  Warning: Could not read secrets file: {e}")
    
    # Validate token format if present
    if token:
        # Check if it looks like a valid GitHub token
        if not (token.startswith('ghp_') or token.startswith('github_pat_') or len(token) > 20):
            print("⚠️  Warning: GitHub token format looks unusual.")
            print("   Expected format: ghp_... or github_pat_...")
    
    return token

GITHUB_TOKEN = load_secrets()

def run_command(cmd, check=True):
    """Run a shell command and return the output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error running command: {cmd}")
        print(f"Error output: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def get_github_repo():
    """Get GitHub repository from git remote."""
    remote_url = run_command("git remote get-url origin", check=False)
    if not remote_url:
        print("Error: No git remote found. Please set up git remote.")
        sys.exit(1)
    
    # Extract owner/repo from various URL formats
    patterns = [
        r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$',
        r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, remote_url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    
    print(f"Error: Could not parse GitHub repo from remote: {remote_url}")
    sys.exit(1)

def validate_url(url):
    """Validate that the URL is a proper URL and looks like a shortcut URL."""
    if not url:
        return False, "URL is empty"
    
    # Check if it looks like a GitHub token (starts with github_pat_ or ghp_)
    if url.startswith("github_pat_") or url.startswith("ghp_"):
        return False, "This looks like a GitHub token, not a shortcut URL. Please enter the iCloud Shortcuts URL (e.g., https://www.icloud.com/shortcuts/...)"
    
    # Check if it's a valid URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL format. Please include http:// or https://"
        
        # Check if it looks like an iCloud shortcuts URL
        if "icloud.com/shortcuts" not in url.lower() and "shortcuts" not in url.lower():
            print("⚠️  Warning: This doesn't look like an iCloud Shortcuts URL.")
            print("   Expected format: https://www.icloud.com/shortcuts/...")
            response = input("   Continue anyway? (y/n): ").strip().lower()
            if response != 'y':
                return False, "URL validation cancelled by user"
        
        return True, None
    except Exception as e:
        return False, f"Invalid URL: {e}"

def pull_latest():
    """Check if we're on the latest version and optionally pull."""
    print("🔍 Checking if we're on the latest version...")
    
    # Fetch latest changes without merging
    run_command("git fetch origin", check=False)
    
    # Get current branch
    current_branch = run_command("git branch --show-current", check=False)
    if not current_branch:
        # Try to detect from remote
        current_branch = run_command("git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'", check=False)
        if not current_branch:
            current_branch = "main"
    
    # Check if we're behind the remote
    behind = run_command(f"git rev-list HEAD..origin/{current_branch} 2>/dev/null | wc -l", check=False)
    behind = behind.strip() if behind else "0"
    
    if behind and int(behind) > 0:
        print(f"⚠️  You are {behind} commit(s) behind origin/{current_branch}")
        response = input("Do you want to pull the latest changes? (y/n): ").strip().lower()
        if response == 'y':
            print("📥 Pulling latest version from git...")
            run_command(f"git pull origin {current_branch}")
            print("✅ Pulled latest changes")
        else:
            print("⏭️  Skipping pull. Continuing with current version...")
    else:
        print("✅ You are already on the latest version")

def download_file(url, output_path):
    """Download a file from URL."""
    print(f"📥 Downloading file from {url}...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"✅ Downloaded to {output_path}")

def generate_qr_code(url, output_path):
    """Generate a QR code from a URL with no border."""
    print(f"🔲 Generating QR code for {url}...")
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,  # No white border
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)
    print(f"✅ QR code saved to {output_path}")

def replace_readme_link(new_link, line_number=57):
    """Replace the shortcut link in README.md."""
    print(f"📝 Replacing link at line {line_number}...")
    
    with open(README_PATH, 'r') as f:
        lines = f.readlines()
    
    # Find and replace the link
    pattern = r'(\*\*Install MessageDict:\*\* )https://[^\s]+'
    for i, line in enumerate(lines):
        if i + 1 == line_number:
            lines[i] = re.sub(pattern, rf'\1{new_link}', line)
            break
    
    with open(README_PATH, 'w') as f:
        f.writelines(lines)
    
    print(f"✅ Link replaced in README.md")

def replace_readme_qr_code(new_qr_url, line_number=59):
    """Replace the QR code image URL in README.md."""
    print(f"📝 Replacing QR code image at line {line_number}...")
    
    with open(README_PATH, 'r') as f:
        lines = f.readlines()
    
    # Find and replace the QR code image URL
    pattern = r'(<img src=")[^"]+(" alt="MessageDict QR Code"[^>]*>)'
    for i, line in enumerate(lines):
        if i + 1 == line_number:
            lines[i] = re.sub(pattern, rf'\1{new_qr_url}\2', line)
            break
    
    with open(README_PATH, 'w') as f:
        f.writelines(lines)
    
    print(f"✅ QR code image URL replaced in README.md")

def upload_qr_to_github(repo, token, qr_path, branch="main"):
    """Upload QR code to GitHub and return the URL."""
    if not token:
        return None
    
    print(f"📤 Uploading QR code to GitHub...")
    
    # Try to determine the default branch
    try:
        default_branch = run_command("git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'", check=False)
        if not default_branch:
            default_branch = branch
    except:
        default_branch = branch
    
    # Read file content
    with open(qr_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode('utf-8')
    
    asset_name = os.path.basename(qr_path)
    file_path = f"assets/{asset_name}"
    
    # Check if file exists
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get file SHA if it exists
    response = requests.get(url, headers=headers)
    sha = None
    if response.status_code == 200:
        sha = response.json().get('sha')
    
    # Upload file
    data = {
        "message": f"Add QR code: {asset_name}",
        "content": content,
        "branch": default_branch
    }
    if sha:
        data["sha"] = sha
    
    response = requests.put(url, json=data, headers=headers)
    
    if response.status_code in [200, 201]:
        file_data = response.json()
        # GitHub API returns content info in 'content' key
        # Construct raw content URL manually (more reliable)
        owner, repo_name = repo.split('/')
        download_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{default_branch}/{file_path}"
        print(f"✅ QR code uploaded: {download_url}")
        return download_url
    else:
        error_msg = response.text
        if response.status_code == 403:
            print(f"⚠️  Failed to upload QR code (403 Forbidden):")
            print(f"   Your GitHub token may not have the required permissions.")
            print(f"   Required scope: 'repo' (full control of private repositories)")
            print(f"   Check your token at: https://github.com/settings/tokens")
            print(f"   Error details: {error_msg}")
        else:
            print(f"⚠️  Failed to upload QR code: {error_msg}")
        return None

def create_github_release(repo, tag, name, body, token, asset_path=None):
    """Create a GitHub release and upload asset."""
    if not token:
        print("⚠️  GITHUB_TOKEN not set. Skipping GitHub release creation.")
        return None
    
    print(f"📦 Creating GitHub release: {tag}...")
    
    # Create release
    url = f"https://api.github.com/repos/{repo}/releases"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": False
    }
    
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 201:
        release_data = response.json()
        print(f"✅ Release created: {release_data['html_url']}")
        
        # Upload asset if provided
        if asset_path and os.path.exists(asset_path):
            upload_url = release_data['upload_url'].split('{')[0]
            asset_name = os.path.basename(asset_path)
            
            with open(asset_path, 'rb') as f:
                files = {'file': (asset_name, f, 'image/png')}
                upload_response = requests.post(
                    f"{upload_url}?name={asset_name}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "image/png"
                    },
                    files=files
                )
            
            if upload_response.status_code == 201:
                print(f"✅ Asset uploaded to release: {asset_name}")
                return upload_response.json().get('browser_download_url')
            else:
                print(f"⚠️  Failed to upload asset: {upload_response.text}")
        return release_data['html_url']
    else:
        print(f"⚠️  Failed to create release: {response.text}")
        if response.status_code == 422:
            print("   Release might already exist. Continuing...")
        return None

def commit_and_push(commit_message):
    """Commit changes and push to git."""
    print("💾 Committing changes...")
    run_command("git add .")
    run_command(f'git commit -m "{commit_message}"')
    print("📤 Pushing to git...")
    run_command("git push origin main || git push origin master")

def create_tag(tag_name):
    """Create and push a git tag."""
    print(f"🏷️  Creating tag: {tag_name}...")
    run_command(f'git tag -a "{tag_name}" -m "{tag_name}"')
    run_command(f'git push origin "{tag_name}"')
    print(f"✅ Tag created and pushed: {tag_name}")

def main():
    """Main function to orchestrate the upload process."""
    print("🚀 Starting MessageDict upload process...\n")
    
    # Step 1: Pull latest from git
    pull_latest()
    
    # Step 2: Get input link
    while True:
        shortcut_url = input("\n🔗 Enter the new shortcut URL: ").strip()
        if not shortcut_url:
            print("Error: No URL provided.")
            continue
        
        # Validate URL
        is_valid, error_msg = validate_url(shortcut_url)
        if is_valid:
            break
        else:
            print(f"❌ {error_msg}")
            print("   Please try again.\n")
    
    # Step 3: Download file
    download_file(shortcut_url, SHORTCUT_PATH)
    
    # Step 4: Replace link in README
    replace_readme_link(shortcut_url)
    
    # Step 5 & 6: Generate QR code from the link and upload
    # Use temporary file for QR code
    qr_code_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png', prefix='message_dict_qr_')
    qr_code_path = qr_code_file.name
    qr_code_file.close()
    generate_qr_code(shortcut_url, qr_code_path)
    
    # Get GitHub repo info
    repo = get_github_repo()
    print(f"📦 Detected GitHub repo: {repo}")
    
    # Upload QR code to GitHub and get URL
    qr_download_url = None
    if GITHUB_TOKEN:
        qr_download_url = upload_qr_to_github(repo, GITHUB_TOKEN, qr_code_path)
        if qr_download_url:
            replace_readme_qr_code(qr_download_url)
        else:
            print("⚠️  QR code upload failed. Will continue without updating QR code URL.")
    else:
        print("⚠️  GITHUB_TOKEN not set. QR code not uploaded to GitHub.")
        print("   You'll need to manually upload and update README.md line 59.")
    
    # Step 7: Get version information
    print("\n📋 Version Information:")
    version_name = input("Enter version name: ").strip()
    tag = input("Enter tag: ").strip()
    changes = input("Enter changes (commit message): ").strip()
    
    if not version_name or not tag or not changes:
        print("Error: Version name, tag, and changes are required.")
        sys.exit(1)
    
    # Create full tag name
    full_tag = f"{version_name} {tag}"
    
    # Step 8: Commit and push
    commit_and_push(changes)
    
    # Step 9: Create tag and release
    create_tag(full_tag)
    
    # Create GitHub release (QR code already uploaded separately)
    if GITHUB_TOKEN:
        create_github_release(
            repo=repo,
            tag=full_tag,
            name=full_tag,
            body=changes,
            token=GITHUB_TOKEN,
            asset_path=qr_code_path
        )
    
    # Clean up temporary QR code file
    try:
        if os.path.exists(qr_code_path):
            os.remove(qr_code_path)
            print("🧹 Cleaned up temporary QR code file")
    except Exception as e:
        print(f"⚠️  Warning: Could not delete temporary QR code file: {e}")
    
    print("\n✅ Upload process completed!")

if __name__ == "__main__":
    main()

