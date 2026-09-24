import os

def count_lines(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return len(f.readlines())
    except Exception:
        return 0

def main():
    workspace = os.path.dirname(os.path.abspath(__file__))
    exclude_dirs = {'.git', 'venv', '__pycache__', '.agents', '.gemini', 'node_modules', 'dist', 'build'}
    
    extension_counts = {}
    total_lines = 0
    total_files = 0
    
    file_details = []
    
    for root, dirs, files in os.walk(workspace):
        # Exclude directories in-place to avoid descending into them
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            # Skip the script itself
            if file == 'count_loc.py':
                continue
                
            ext = os.path.splitext(file)[1].lower()
            # We want to count code, markup, styling and config files
            if ext in ['.py', '.html', '.css', '.js', '.sql', '.txt', '.json', '.md', '.yml', '.yaml']:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, workspace)
                
                # Skip files inside hidden/excluded structures
                if any(part.startswith('.') for part in rel_path.split(os.sep)):
                    continue
                    
                lines = count_lines(filepath)
                extension_counts[ext] = extension_counts.get(ext, 0) + lines
                total_lines += lines
                total_files += 1
                file_details.append((rel_path, ext, lines))
                
    print("=" * 60)
    print(f" LOGI-TRACK Project Lines of Code (LOC) Summary")
    print("=" * 60)
    print(f"Total Lines of Code: {total_lines}")
    print(f"Total Files Analyzed: {total_files}")
    print("-" * 60)
    print("Breakdown by Extension:")
    for ext, count in sorted(extension_counts.items(), key=lambda x: x[1], reverse=True):
        name = {
            '.py': 'Python Source',
            '.html': 'HTML Templates',
            '.css': 'CSS Stylesheets',
            '.js': 'JavaScript Code',
            '.sql': 'SQL Database Schema',
            '.txt': 'Text Config/Reqs',
            '.json': 'JSON Configs',
            '.md': 'Markdown Documentation'
        }.get(ext, ext or 'no extension')
        print(f"  {ext:<7} ({name:<25}): {count:>5} lines")
        
    print("-" * 60)
    print("Top 15 Largest Files:")
    for path, ext, lines in sorted(file_details, key=lambda x: x[2], reverse=True)[:15]:
        print(f"  {lines:>5} lines - {path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
