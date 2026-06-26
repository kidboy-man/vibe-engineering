# Obsidian Setup — Optional Visual Browser

Obsidian is an optional visual browser for the vault. It provides graph view, wikilink navigation, and search. The vault works fully without it.

## Install

### Linux

- **AppImage**: Download from [obsidian.md/download](https://obsidian.md/download)
- **Flatpak**: `flatpak install flathub md.obsidian.Obsidian`

### macOS

```bash
brew install --cask obsidian
```

### Windows (Non-WSL)

Download installer from [obsidian.md/download](https://obsidian.md/download).

## WSL2 Warning

If you are running Linux inside WSL2 on Windows 11:

**Do NOT use the Windows Obsidian binary** pointing at `\\wsl$\...\vault` via UNC path. It fails with:

```
Error: EISDIR: illegal operation on a directory, watch '\\wsl$\...\vault'
```

This is a confirmed, unfixed bug (Obsidian forum thread 8580, ongoing since 2021). The Windows file-watcher cannot watch 9P-mounted network shares.

**Correct approach for WSL2:** Install Obsidian inside WSL2 using WSLg (Windows 11+ supports Linux GUI apps natively):

```bash
# Download and install the Linux .deb
deb_url=$(curl -s https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest \
  | grep -oE 'https://[^"]*obsidian_[0-9.]+_amd64\.deb' | head -1)
wget "$deb_url" -O /tmp/obsidian.deb
sudo apt install -y /tmp/obsidian.deb
rm /tmp/obsidian.deb
```

Launch from Windows Start Menu as "Obsidian (Ubuntu)" or run `obsidian` from the WSL2 terminal.

## Set as Default Vault

After opening Obsidian:

1. Manage Vaults → Open folder as vault → select `<vault>`
2. Edit `~/.config/obsidian/obsidian.json` to add `"lastOpenVault": "<vault-id>"` so Obsidian defaults to this vault on launch.

## Not Required

The vault is plain Markdown files on disk. All AI agents read and write them directly. Obsidian is a convenience layer, not a dependency.
