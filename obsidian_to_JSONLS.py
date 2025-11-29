import sys
import os
import re
import frontmatter
from urllib.parse import quote
from rdflib import Graph, Namespace, RDF, SKOS, Literal, URIRef

# --- CONFIGURATION ---
BASE_URI = "http://example.org/kb/"
LANG = "en"

def clean_uri(label):
    """Sanitize string to create a valid URI suffix."""
    # Remove [[ and ]] if they exist, then URI encode
    clean = label.replace("[[", "").replace("]]", "")
    return URIRef(f"{BASE_URI}{quote(clean.replace(' ', '-'))}")

def parse_links(value):
    """
    Extracts links from YAML values. 
    Handles: "[[Link]]", ["[[Link A]]", "[[Link B]]"], or plain strings.
    """
    if not value:
        return []
    
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []

    links = []
    for item in items:
        # Regex to grab content inside [[...]] if present, else take whole string
        match = re.search(r"\[\[([^\|\]]+)(\|[^\]]+)?\]\]", item)
        if match:
            links.append(match.group(1))
        else:
            # Assume it's a valid concept name even without brackets
            links.append(item)
    return links

def generate_hierarchical_skos(file_path):
    # 1. SETUP GRAPH
    g = Graph()
    g.bind("skos", SKOS)
    
    filename_raw = os.path.splitext(os.path.basename(file_path))[0]
    
    # Load Markdown with Frontmatter
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return

    # 2. CREATE MAIN CONCEPT
    subject_uri = clean_uri(filename_raw)
    g.add((subject_uri, RDF.type, SKOS.Concept))
    g.add((subject_uri, SKOS.prefLabel, Literal(filename_raw, lang=LANG)))

    # 3. PROCESS METADATA (The "Gold Standard" Fields)
    
    # Aliases -> altLabel
    if post.get('aliases'):
        aliases = post['aliases'] if isinstance(post['aliases'], list) else [post['aliases']]
        for alias in aliases:
            g.add((subject_uri, SKOS.altLabel, Literal(alias, lang=LANG)))

    # Definitions
    if post.get('definition'):
        g.add((subject_uri, SKOS.definition, Literal(post['definition'], lang=LANG)))
    
    if post.get('scopeNote'):
        g.add((subject_uri, SKOS.scopeNote, Literal(post['scopeNote'], lang=LANG)))

    # --- HIERARCHY LOGIC ---
    
    # Broader (Parents)
    broader_links = parse_links(post.get('broader'))
    for link in broader_links:
        g.add((subject_uri, SKOS.broader, clean_uri(link)))

    # Narrower (Children)
    narrower_links = parse_links(post.get('narrower'))
    for link in narrower_links:
        g.add((subject_uri, SKOS.narrower, clean_uri(link)))

    # Related (Associations)
    related_links = parse_links(post.get('related'))
    for link in related_links:
        g.add((subject_uri, SKOS.related, clean_uri(link)))

    # Exact Match (External URIs like Wikidata)
    # We treat these differently (don't convert to internal BASE_URI)
    exact_match = post.get('exactMatch')
    if exact_match:
        matches = exact_match if isinstance(exact_match, list) else [exact_match]
        for uri in matches:
            try:
                g.add((subject_uri, SKOS.exactMatch, URIRef(uri)))
            except:
                pass # Skip invalid URIs

    # 4. EXPORT JSON-LD
    jsonld_data = g.serialize(format='json-ld', indent=4)
    output_json_path = f"{filename_raw}.jsonld"
    with open(output_json_path, "w", encoding="utf-8") as f:
        f.write(jsonld_data)
    print(f"✔ SKOS JSON-LD Generated: {output_json_path}")

    # 5. EXPORT HTML VISUALIZATION
    # Generate HTML list items for relationships
    def make_list(links):
        return "".join([f'<li><a href="{l.replace(" ", "-")}.html">{l}</a></li>' for l in links]) if links else "<li>None</li>"

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{filename_raw} (SKOS)</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; max-width: 700px; margin: 2rem auto; background: #f4f4f4; }}
        .card {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ margin-top: 0; color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .tag {{ background: #e1ecf4; color: #39739d; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
        .section {{ margin-top: 20px; }}
        .section h3 {{ font-size: 0.9rem; text-transform: uppercase; color: #888; margin-bottom: 5px; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ margin-bottom: 5px; }}
        a {{ text-decoration: none; color: #0366d6; }}
        a:hover {{ text-decoration: underline; }}
    </style>
    <script type="application/ld+json">
    {jsonld_data}
    </script>
</head>
<body>
    <div class="card">
        <h1>{filename_raw}</h1>
        
        <div class="section">
            <h3>Definition</h3>
            <p>{post.get('definition', 'No definition provided.')}</p>
        </div>

        <div style="display: flex; gap: 20px;">
            <div class="section" style="flex:1">
                <h3>⬆ Broader (Parent)</h3>
                <ul>{make_list(broader_links)}</ul>
            </div>
            <div class="section" style="flex:1">
                <h3>⬇ Narrower (Children)</h3>
                <ul>{make_list(narrower_links)}</ul>
            </div>
        </div>

        <div class="section">
            <h3>↔ Related</h3>
            <ul>{make_list(related_links)}</ul>
        </div>
        
        <div class="section">
            <h3>External ID</h3>
            <p><a href="{exact_match if exact_match else '#'}">{exact_match if exact_match else 'None'}</a></p>
        </div>
    </div>
</body>
</html>
    """
    
    output_html_path = f"{filename_raw}.html"
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✔ HTML Visualization Generated: {output_html_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python obsidian_skos_hierarchy.py <filename.md>")
    else:
        generate_hierarchical_skos(sys.argv[1])