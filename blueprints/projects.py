import os
from flask import Blueprint, render_template, jsonify
import database

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/projects')
def projects():
    return render_template('projects.html')


@projects_bp.route('/api/projects')
def api_projects():
    db_projects = database.list_projects()
    
    # Group by category
    categories = {}
    for p in db_projects:
        cat = p.get('category', 'General')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p)
    
    # Convert to list of objects: [ { "name": "...", "projects": [...] }, ... ]
    # Sort categories: Infrastructure first, then Tools, then others
    sort_map = {"Infrastructure": 0, "Tools": 1, "AI / Lab": 2, "General": 3}
    cat_list = []
    for cat, projs in categories.items():
        cat_list.append({
            "name": cat,
            "sort": sort_map.get(cat, 99),
            "projects": projs
        })
    
    cat_list.sort(key=lambda x: x['sort'])
    
    return jsonify({
        'projects': db_projects, # Keep original for compatibility if needed
        'categories': cat_list
    })
