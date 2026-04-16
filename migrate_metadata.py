import os
import json

# Set dummy env vars for migration run
os.environ.setdefault('SECRET_KEY', 'migration-only')
os.environ.setdefault('UPLINK_PASSWORD_HASH', 'migration-only')
os.environ.setdefault('CLAUDE_PASSWORD_HASH', 'migration-only')
os.environ.setdefault('ANTHROPIC_API_KEY', 'migration-only')

import database

def migrate():
    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    
    # 1. Migrate Files
    metadata_file = os.path.join(instance_path, 'files_metadata.json')
    if os.path.exists(metadata_file):
        print(f"Loading metadata from {metadata_file}...")
        with open(metadata_file, 'r') as f:
            data = json.load(f)
        files = data.get('files', [])
        print(f"Migrating {len(files)} file entries to SQLite...")
        database.init_db()
        count = 0
        for f in files:
            if not database.get_file(f['id']):
                database.add_file(
                    file_id=f['id'],
                    name=f['name'],
                    stored_name=f['stored_name'],
                    size=f['size'],
                    uploaded=f['uploaded'],
                    uploader=f.get('uploader', 'Anonymous')
                )
                count += 1
        print(f"Successfully migrated {count} file entries.")
        backup_file = metadata_file + ".bak"
        os.rename(metadata_file, backup_file)
    else:
        print("No file metadata to migrate.")

    # 2. Migrate Projects
    projects_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects.json')
    if os.path.exists(projects_file):
        print(f"Loading projects from {projects_file}...")
        with open(projects_file, 'r') as f:
            data = json.load(f)
        
        projects = data.get('projects', [])
        count = 0
        database.init_db()
        
        for idx, p in enumerate(projects):
            pid = p.get('id') or p['name'].lower().replace(' ', '_')
            database.add_project(
                pid=pid,
                name=p['name'],
                description=p.get('description', ''),
                # Handle detail_url as fallback if url is missing
                url=p.get('url') or p.get('detail_url') or '#',
                icon=p.get('icon', 'package'),
                category=p.get('category', 'General'),
                status=p.get('status', 'online'),
                sort_order=idx
            )
            count += 1
        print(f"Successfully migrated {count} projects.")
    else:
        print("No projects.json found to migrate.")

if __name__ == "__main__":
    migrate()
