#!/usr/bin/env python3
"""
Work Prompt Manager - Helper script for managing prompts.json

Usage:
    python prompt_manager.py list
    python prompt_manager.py add
    python prompt_manager.py update <index>
    python prompt_manager.py delete <index>
    python prompt_manager.py export
"""

import json
import sys
from pathlib import Path
from typing import List, Dict


class PromptManager:
    def __init__(self, file_path: str = "prompts.json"):
        self.file_path = Path(file_path)
        self.prompts = self._load_prompts()
    
    def _load_prompts(self) -> List[Dict]:
        """Load prompts from JSON file"""
        if not self.file_path.exists():
            print(f"Creating new {self.file_path}")
            return []
        
        with open(self.file_path, 'r') as f:
            return json.load(f)
    
    def _save_prompts(self):
        """Save prompts to JSON file"""
        with open(self.file_path, 'w') as f:
            json.dump(self.prompts, f, indent=2)
        print(f"✓ Saved to {self.file_path}")
    
    def list_prompts(self):
        """Display all prompts"""
        if not self.prompts:
            print("No prompts found.")
            return
        
        print(f"\n{'='*60}")
        print(f"Total prompts: {len(self.prompts)}")
        print(f"{'='*60}\n")
        
        for idx, prompt in enumerate(self.prompts):
            print(f"[{idx}] {prompt['title']}")
            print(f"    Theme: {prompt['theme']}")
            print(f"    Preview: {prompt['details'][:60]}...")
            print()
    
    def add_prompt(self):
        """Add a new prompt interactively"""
        print("\n--- Add New Prompt ---\n")
        
        theme = input("Theme (e.g., Leadership, Strategy): ").strip()
        if not theme:
            print("Theme is required.")
            return
        
        title = input("Title: ").strip()
        if not title:
            print("Title is required.")
            return
        
        print("Details (press Enter twice when done):")
        details_lines = []
        while True:
            line = input()
            if line == "" and (not details_lines or details_lines[-1] == ""):
                break
            details_lines.append(line)
        
        # Remove trailing empty line
        if details_lines and details_lines[-1] == "":
            details_lines.pop()
        
        details = "\n".join(details_lines)
        
        if not details:
            print("Details are required.")
            return
        
        new_prompt = {
            "theme": theme,
            "title": title,
            "details": details
        }
        
        self.prompts.append(new_prompt)
        self._save_prompts()
        print(f"\n✓ Added prompt: {title}")
    
    def update_prompt(self, index: int):
        """Update an existing prompt"""
        if index < 0 or index >= len(self.prompts):
            print(f"Invalid index. Use 0-{len(self.prompts)-1}")
            return
        
        prompt = self.prompts[index]
        print(f"\n--- Update Prompt [{index}] ---\n")
        print(f"Current title: {prompt['title']}")
        print(f"Current theme: {prompt['theme']}\n")
        
        theme = input(f"Theme [{prompt['theme']}]: ").strip()
        title = input(f"Title [{prompt['title']}]: ").strip()
        
        print(f"Details (leave blank to keep current, press Enter twice when done):")
        print(f"Current: {prompt['details'][:100]}...\n")
        
        details_lines = []
        while True:
            line = input()
            if line == "" and (not details_lines or details_lines[-1] == ""):
                break
            details_lines.append(line)
        
        # Remove trailing empty line
        if details_lines and details_lines[-1] == "":
            details_lines.pop()
        
        details = "\n".join(details_lines) if details_lines else None
        
        # Update only if new value provided
        if theme:
            prompt['theme'] = theme
        if title:
            prompt['title'] = title
        if details:
            prompt['details'] = details
        
        self._save_prompts()
        print(f"\n✓ Updated prompt: {prompt['title']}")
    
    def delete_prompt(self, index: int):
        """Delete a prompt"""
        if index < 0 or index >= len(self.prompts):
            print(f"Invalid index. Use 0-{len(self.prompts)-1}")
            return
        
        prompt = self.prompts[index]
        confirm = input(f"Delete '{prompt['title']}'? (y/n): ").lower()
        
        if confirm == 'y':
            self.prompts.pop(index)
            self._save_prompts()
            print(f"✓ Deleted prompt: {prompt['title']}")
        else:
            print("Cancelled.")
    
    def export_prompts(self):
        """Export prompts to a formatted text file"""
        output_file = "prompts_export.txt"
        
        with open(output_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("WORK PROMPTS EXPORT\n")
            f.write("=" * 60 + "\n\n")
            
            for idx, prompt in enumerate(self.prompts):
                f.write(f"[{idx}] {prompt['title']}\n")
                f.write(f"Theme: {prompt['theme']}\n")
                f.write("-" * 60 + "\n")
                f.write(f"{prompt['details']}\n")
                f.write("\n" + "=" * 60 + "\n\n")
        
        print(f"✓ Exported to {output_file}")


def main():
    manager = PromptManager()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python prompt_manager.py list")
        print("  python prompt_manager.py add")
        print("  python prompt_manager.py update <index>")
        print("  python prompt_manager.py delete <index>")
        print("  python prompt_manager.py export")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "list":
        manager.list_prompts()
    
    elif command == "add":
        manager.add_prompt()
    
    elif command == "update":
        if len(sys.argv) < 3:
            print("Usage: python prompt_manager.py update <index>")
            sys.exit(1)
        try:
            index = int(sys.argv[2])
            manager.update_prompt(index)
        except ValueError:
            print("Index must be a number")
    
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: python prompt_manager.py delete <index>")
            sys.exit(1)
        try:
            index = int(sys.argv[2])
            manager.delete_prompt(index)
        except ValueError:
            print("Index must be a number")
    
    elif command == "export":
        manager.export_prompts()
    
    else:
        print(f"Unknown command: {command}")
        print("Available commands: list, add, update, delete, export")


if __name__ == "__main__":
    main()
