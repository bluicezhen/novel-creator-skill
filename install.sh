#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法：
  ./install.sh <目标项目目录>

示例：
  ./install.sh /exam/code
USAGE
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

TARGET_ROOT="$1"
if [[ -z "$TARGET_ROOT" ]]; then
  usage >&2
  exit 2
fi

mkdir -p "$TARGET_ROOT"
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd -P)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DEST_CLAUDE="$TARGET_ROOT/.claude"
DEST_SKILL="$DEST_CLAUDE/skills/novel-creator-skill"
DEST_COMMANDS="$DEST_CLAUDE/commands"

mkdir -p "$DEST_SKILL" "$DEST_COMMANDS"

copy_path() {
  local src="$1"
  local dest_dir="$2"
  if [[ -e "$src" ]]; then
    cp -R "$src" "$dest_dir/"
  fi
}

copy_path "$SCRIPT_DIR/SKILL.md" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/novel-creator.md" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/novel-creator.json" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/README.md" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/CLAUDE.md" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/references" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/scripts" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/templates" "$DEST_SKILL"
copy_path "$SCRIPT_DIR/assets" "$DEST_SKILL"

shopt -s nullglob
for command_file in "$SCRIPT_DIR/.claude/commands"/*.md; do
  cp -f "$command_file" "$DEST_COMMANDS/"
done
shopt -u nullglob

cat <<EOF
安装完成
skill=$DEST_SKILL
commands=$DEST_COMMANDS
EOF
