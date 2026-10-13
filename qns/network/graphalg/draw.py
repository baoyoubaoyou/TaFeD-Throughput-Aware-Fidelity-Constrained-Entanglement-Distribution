import pandas as pd
import webbrowser
import os
import json
import copy
import math


def draw(nl, ll, filename):
    """
    draw network topology based on provided Node list and Link list
    Args:
        nl: list of Qnodes
        ll: list of QuantumChannel
        filename: path of the output file
    Return:
        HTML file generated and opened
    """

    node_list = []
    node_ref_to_id = {}
    node_name_to_id = {}

    for i, node_obj in enumerate(nl):
        new_id = i + 1
        name = getattr(node_obj, 'name', f"Node_{new_id}")
        raw_apps = getattr(node_obj, 'apps', [])
        processed_apps_labels = []

        if raw_apps:
            if not isinstance(raw_apps, list):
                raw_apps = [raw_apps]

            for app_obj in raw_apps:
                app_index = 0
                app_label = getattr(app_obj, 'name', f"Node_app{app_index+1}")
                processed_apps_labels.append(str(app_label))
                app_index = app_index + 1

        node_ref_to_id[node_obj] = new_id
        node_name_to_id[name] = new_id
        node_name_to_id[str(node_obj)] = new_id

        node_list.append({
            "id": new_id,
            "name": name,
            "apps": processed_apps_labels,
            "original_obj": str(node_obj)
        })

    edge_list = []
    for i, link_obj in enumerate(ll):
        src_raw, dest_raw = getattr(link_obj, "node_list", None)

        if src_raw is None or dest_raw is None:
            print(f"Warning: Skipping link {link_obj}, cannot find src/dest attributes.")
            continue
        src_id = None
        dest_id = None

        if src_raw in node_ref_to_id:
            src_id = node_ref_to_id[src_raw]
        elif dest_raw in node_ref_to_id:
            dest_id = node_ref_to_id[dest_raw]

        if src_id is None:
            src_str = str(src_raw)
            if hasattr(src_raw, 'name'):
                src_str = src_raw.name
            if src_str in node_name_to_id:
                src_id = node_name_to_id[src_str]

        if dest_id is None:
            dest_str = str(dest_raw)
            if hasattr(dest_raw, 'name'):
                dest_str = dest_raw.name
            if dest_str in node_name_to_id:
                dest_id = node_name_to_id[dest_str]

        if src_id is None or dest_id is None:
            print(f"Warning: Skipping link, could not map nodes: {src_raw} -> {dest_raw}")
            continue

        link_name = getattr(link_obj, 'name', f"Link_{src_id}_{dest_id}")
        bw = getattr(link_obj, 'bandwidth', 1.0)
        fid = getattr(link_obj, 'fidelity', 1.0)

        edge_list.append({
            "id": f"e{i}",
            "src": src_id,
            "dest": dest_id,
            "bandwidth": bw,
            "name": link_name,
            "fidelity": fid
        })

    # --- REPLACED NETWORKX WITH SIMPLE CIRCULAR LAYOUT ---
    vis_nodes = copy.deepcopy(node_list)
    vis_edges = copy.deepcopy(edge_list)

    node_count = len(vis_nodes)
    radius = 1000  # Visual scale for initial circle

    for i, n in enumerate(vis_nodes):
        # Calculate angle for circular distribution
        angle = 2 * math.pi * i / max(1, node_count)

        # Assign initial coordinates
        n['x'] = radius * math.cos(angle)
        n['y'] = radius * math.sin(angle)

        n['label'] = " "
        n['_realLabel'] = n['name']

        apps_str = ", ".join(n['apps']) if n['apps'] else "None"
        n['title'] = f"ID:{n['id']}  Name:{n['name']}\nApps: {apps_str}"

    for e in vis_edges:
        e['from'] = e['src']
        e['to'] = e['dest']
        e['label'] = " "
        e['_realLabel'] = e['name']
        e['title'] = (
            f"Name:{e['name']}\n"
            f"Bandwidth:{e['bandwidth']}\n"
            f"Fidelity:{e['fidelity']}"
        )

    # Python List Comprehension: Split into multiple lines
    table_nodes_data = [
        {"id": n['id'], "name": n['name'], "apps": ", ".join(n['apps'])}
        for n in node_list
    ]

    table_edges_data = [
        {
            "name": e['name'],
            "src": e['src'],
            "dest": e['dest'],
            "bandwidth": e['bandwidth'],
            "fidelity": e['fidelity']
        }
        for e in edge_list
    ]

    df_nodes = pd.DataFrame(table_nodes_data)
    df_edges = pd.DataFrame(table_edges_data)

    # Pandas to_html: Split arguments
    node_table_html = df_nodes.to_html(
        classes='custom-table node-table-row',
        index=False,
        table_id="nodeTable",
        border=0
    )
    edge_table_html = df_edges.to_html(
        classes='custom-table edge-table-row',
        index=False,
        table_id="edgeTable",
        border=0
    )

    physics_options = {
        "physics": {
            "enabled": True,
            "solver": "barnesHut",
            "barnesHut": {
                "gravitationalConstant": -8000,
                "centralGravity": 0.3,
                "springLength": 95,
                "springConstant": 0.04,
                "damping": 0.09,
                "avoidOverlap": 0.1
            },
            "stabilization": {"enabled": True, "iterations": 100}
        }
    }

    js_nodes_data = json.dumps(vis_nodes)
    js_edges_data = json.dumps(vis_edges)
    js_physics_options = json.dumps(physics_options["physics"])

    # CSS Styles
    css_styles = """
    <style>
        * { box-sizing: border-box; }
        body, html {
            margin: 0; padding: 0; height: 100vh; width: 100vw;
            overflow: hidden;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        #app-container { display: flex; width: 100%; height: 100%; }

        #left-panel {
            width: 300px; min-width: 250px; background: #2c3e50; color: #ecf0f1;
            display: flex; flex-direction: column; border-right: 1px solid #1a252f;
            z-index: 20;
        }
        .panel-content { padding: 15px; overflow-y: auto; flex: 1; }

        #center-panel {
            flex: 1; min-width: 300px; position: relative; background: #fdfdfd;
        }
        #mynetwork { width: 100%; height: 100%; outline: none; }

        #right-panel {
            width: 450px; min-width: 200px; background: #f4f6f7;
            border-left: 1px solid #bdc3c7; display: flex; flex-direction: column;
        }

        .resizer {
            width: 5px; background: #95a5a6; cursor: col-resize; z-index: 10;
            transition: 0.2s;
        }
        .resizer:hover { background: #3498db; }

        /* Controls */
        h3 {
            border-bottom: 2px solid #34495e; padding-bottom: 8px; margin-top: 0;
            font-size: 16px; color: #f1c40f;
        }
        h4 {
            color: #1abc9c; margin: 15px 0 5px 0; border-bottom: 1px dashed #7f8c8d;
            padding-bottom: 3px; font-size: 14px;
        }
        label {
            font-size: 12px; color: #bdc3c7; display: block; margin-top: 8px;
        }
        input, select, button {
            width: 100%; padding: 8px; margin-top: 4px; border-radius: 4px;
            border: 1px solid #34495e; font-size: 13px; box-sizing: border-box
        }
        button {
            background: #27ae60; color: white; border: none; cursor: pointer;
            margin-top: 12px; font-weight: bold; transition: 0.2s;
        }
        button:hover { background: #2ecc71; }
        .btn-blue { background: #2980b9; }
        .btn-blue:hover { background: #3498db; }
        .btn-orange { background: #e67e22; }
        .btn-orange:hover { background: #d35400; }

        .checkbox-container {
            display: flex; align-items: center; margin-top: 10px; font-size: 13px;
            background: rgba(0,0,0,0.2); padding: 5px; border-radius: 4px;
        }
        .checkbox-container input { width: auto; margin-right: 8px; cursor: pointer;}

        /* Path Results */
        #path-results-container {
            margin-top: 15px; border-top: 1px solid #34495e; padding-top: 10px;
        }
        .path-item {
            background: #34495e; padding: 10px; margin-top: 8px; border-radius: 4px;
            cursor: pointer; font-size: 12px; border-left: 4px solid transparent;
            transition: 0.2s;
        }
        .path-item:hover { background: #3d566e; }
        .path-active {
            border-left: 4px solid #e74c3c; background: #2c3e50;
            box-shadow: 0 0 5px rgba(0,0,0,0.5);
        }
        .path-detail {
            color: #bdc3c7; margin-top: 4px; font-family: monospace; font-size: 11px;
            word-break: break-all;
        }

        /* Tables */
        .table-wrapper {
            flex: 1; overflow: auto; padding: 0; display: flex; flex-direction: column;
        }
        .table-header-title {
            padding: 10px; background: #e9ecef; font-weight: bold;
            border-bottom: 1px solid #ddd; flex-shrink: 0;
        }

        table.custom-table {
            width: 100%; border-collapse: collapse; background: white;
            font-size: 12px; table-layout: fixed;
        }
        table.custom-table th {
            background: #009879; color: white; padding: 8px; text-align: left;
            position: sticky; top: 0; z-index: 2;
        }
        table.custom-table td {
            padding: 8px; border-bottom: 1px solid #eee; color: #333;
            word-wrap: break-word; cursor: pointer;
        }
        table.custom-table tr:hover { background: #fffde7; }
        table.custom-table tr.selected {
            background: #fff3cd !important; border-left: 4px solid #FFD700 !important;
        }

        /* Modals */
        .modal {
            display: none; position: fixed; z-index: 100; left: 0; top: 0;
            width: 100%; height: 100%; background: rgba(0,0,0,0.5);
        }
        .modal-content {
            background: white; margin: 10% auto; padding: 25px; width: 320px;
            border-radius: 8px; position: relative;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        .close-btn {
            position: absolute; right: 15px; top: 10px; font-size: 24px;
            cursor: pointer; color: #aaa;
        }
        .close-btn:hover { color: #333; }
    </style>
    """

    html_structure = f"""
    <div id="app-container">
        <div id="left-panel">
            <div class="panel-content">
                <h3> Control Panel</h3>
                <div style="font-size:11px; color:#aaa; margin-bottom:10px;">
                    Nodes: {len(nl)} | Edges: {len(ll)}
                </div>

                <h4> Display</h4>
                <div class="checkbox-container"
                     onclick="document.getElementById('label-toggle').click()">
                    <input type="checkbox" id="label-toggle" onchange="toggleLabels(this)">
                    <span>Show Labels</span>
                </div>
                <div class="checkbox-container"
                     onclick="document.getElementById('physics-toggle').click()">
                    <input type="checkbox" id="physics-toggle"
                           onchange="togglePhysics(this)" checked>
                    <span>Live Physics</span>
                </div>

                <h4> Visual Style</h4>
                <input id="style-name" placeholder="Target Name (e.g. Node_01)">
                <input type="color" id="style-color" value="#ff0000"
                       style="height:35px; padding:2px; margin-top:5px;">
                <button onclick="applyColorByName()">Apply Color</button>

                <h4> Pathfinding (Edge Disjoint)</h4>
                <div style="font-size:11px; color:#aaa; margin-bottom:5px;">
                    Algorithm: Find Path -> Remove Edges -> Repeat
                </div>
                <div style="display:flex; gap:5px;">
                    <input id="path-start" placeholder="Start Node Name/ID">
                    <input id="path-end" placeholder="End Node Name/ID">
                </div>

                <label>Metric:</label>
                <select id="path-weight-metric">
                    <option value="bandwidth">Bandwidth (Minimize Cost)</option>
                    <option value="hops">Hop Count</option>
                    <option value="fidelity">Max Log-Fidelity</option>
                </select>
                <label>Max K Paths (Disjoint):</label>
                <input type="number" id="path-k" value="3" min="1" max="100">

                <button class="btn-orange" onclick="calculateKShortestPaths()">
                    Calculate Path
                </button>
                <button class="btn-blue" onclick="resetGraph()"> Reset View</button>

                <div id="path-results-container">
                    <div style="font-size:12px; color:#aaa; text-align:center; padding:10px;">
                        Results will appear here
                    </div>
                </div>

                <br>
                <div style="display:flex; gap:5px;">
                    <button onclick="openModal('nodeModal')"> Node</button>
                    <button onclick="openModal('edgeModal')"> Edge</button>
                </div>
            </div>
        </div>

        <div class="resizer" id="resizer-left"></div>
        <div id="center-panel"><div id="mynetwork"></div></div>
        <div class="resizer" id="resizer-right"></div>

        <div id="right-panel">
            <div class="table-wrapper" style="border-bottom: 4px solid #ddd;">
                <div class="table-header-title"> Node List (Click to Toggle)</div>
                {node_table_html}
            </div>
            <div class="table-wrapper">
                <div class="table-header-title"> Edge List (Click to Toggle)</div>
                {edge_table_html}
            </div>
        </div>
    </div>

    <div id="nodeModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeModal('nodeModal')">&times;</span>
            <h3>Add Node (Visual Only)</h3>
            <input id="new-node-id" placeholder="ID (Integer)">
            <input id="new-node-name" placeholder="Name">
            <input id="new-node-apps" placeholder="Apps">
            <button onclick="addNode()">Confirm Add</button>
        </div>
    </div>

    <div id="edgeModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeModal('edgeModal')">&times;</span>
            <h3>Add Connection (Visual Only)</h3>
            <input id="new-edge-src" placeholder="Src ID">
            <input id="new-edge-dest" placeholder="Dest ID">
            <input id="new-edge-bandwidth" type="number" placeholder="Bandwidth" value="10">
            <input id="new-edge-fidelity" type="number" step="0.01" min="0" max="1"
                   placeholder="Fidelity" value="0.99">
            <button onclick="addEdge()">Confirm Connect</button>
        </div>
    </div>
    """

    # JS Logic
    js_logic = f"""
    <script type="text/javascript"
            src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js">
    </script>
    <script type="text/javascript">
        var nodes = new vis.DataSet({js_nodes_data});
        var edges = new vis.DataSet({js_edges_data});
        var container = document.getElementById('mynetwork');

        var HIGHLIGHT_COLOR = '#FFD700';
        var HIGHLIGHT_BORDER = '#E67E22';
        var PATH_COLOR = '#e74c3c';

        var options = {{
            nodes: {{
                shape: 'dot',
                size: 20,
                font: {{ size: 14 }},
                color: {{
                    background: '#97C2FC',
                    border: '#2B7CE9',
                    highlight: {{
                        background: HIGHLIGHT_COLOR,
                        border: HIGHLIGHT_BORDER
                    }}
                }}
            }},
            edges: {{
                font: {{ size: 12, align: 'middle' }},
                color: {{
                    color: '#2B7CE9',
                    hover: '#848484',
                    highlight: HIGHLIGHT_COLOR
                }},
                smooth: {{ enabled: true, type: 'dynamic' }}
            }},
            physics: {js_physics_options},
            interaction: {{
                hover: true,
                tooltipDelay: 200,
                zoomView: true,
                dragView: true,
                dragNodes: true
            }}
        }};

        var network = new vis.Network(container,
                                      {{ nodes: nodes, edges: edges }},
                                      options);

        // --- Helper: Find Node ID by Name or ID ---
        function resolveNodeId(input) {{
            if(!input) return null;
            input = input.toString().trim();
            // Try explicit Integer ID match first
            if(!isNaN(input)) {{
                let id = parseInt(input);
                if(nodes.get(id)) return id;
            }}
            // Try Name match
            let node = nodes.get().find(n => n.name === input);
            if(node) return node.id;
            return null;
        }}

        // --- Build Graph Helper ---
        function buildGraphFromData(nodeData, edgeData, metric) {{
            var graph = {{}};
            nodeData.getIds().forEach(id => graph[id] = {{}});
            edgeData.get().forEach(e => {{
                let w = 1;
                if(metric === 'bandwidth') w = (e.bandwidth ? 1000/e.bandwidth : 1);
                else if (metric === 'fidelity') {{
                    let f = e.fidelity || 1.0;
                    if(f <= 0) f = 0.0001; if(f > 1) f = 1.0;
                    w = -Math.log(f);
                }}

                // Undirected Graph Logic
                if(!graph[e.from]) graph[e.from]={{}};
                if(!graph[e.to]) graph[e.to]={{}};

                graph[e.from][e.to] = {{weight: w, id: e.id}};
                graph[e.to][e.from] = {{weight: w, id: e.id}};
            }});
            return graph;
        }}

        // --- Pathfinding: Edge Disjoint Algorithm (Greedy) ---
        function calculateKShortestPaths() {{
            var startInput = document.getElementById('path-start').value;
            var endInput = document.getElementById('path-end').value;
            var K = parseInt(document.getElementById('path-k').value) || 1;
            var metric = document.getElementById('path-weight-metric').value;

            var start = resolveNodeId(startInput);
            var end = resolveNodeId(endInput);

            if(!start || !end) {{ alert("Start or End node not found!"); return; }}
            if(start === end) {{ alert("Start and End are the same!"); return; }}

            // 1. Build initial local graph
            var localGraph = buildGraphFromData(nodes, edges, metric);
            var foundPaths = [];

            for(let k=0; k < K; k++) {{
                // 2. Run Dijkstra on current graph
                var result = dijkstra(localGraph, start, end);

                if(!result) break; // No more paths possible (graph disconnected)

                foundPaths.push(result);

                // 3. REMOVE EDGES used in this path from localGraph
                let pathNodes = result.nodes;
                for(let i=0; i < pathNodes.length - 1; i++) {{
                    let u = pathNodes[i];
                    let v = pathNodes[i+1];

                    // Delete forward edge
                    if(localGraph[u]) delete localGraph[u][v];
                    // Delete reverse edge (undirected)
                    if(localGraph[v]) delete localGraph[v][u];
                }}
            }}

            displayPathResults(foundPaths, metric);
        }}

        function dijkstra(g, s, e) {{
            var dist = {{}}, prev = {{}}, pq = new Set(Object.keys(g).map(Number));
            for(let k in g) dist[k] = Infinity;
            dist[s] = 0;

            while(pq.size) {{
                let u = null;
                for(let n of pq) if(u===null || dist[n] < dist[u]) u = n;

                if(u === e || dist[u] === Infinity) break;
                pq.delete(u);

                if(g[u]) {{
                    for(let v in g[u]) {{
                        let v_int = parseInt(v);
                        if(pq.has(v_int)) {{
                            let alt = dist[u] + g[u][v].weight;
                            if(alt < dist[v_int]) {{
                                dist[v_int] = alt;
                                prev[v_int] = u;
                            }}
                        }}
                    }}
                }}
            }}
            if(dist[e] === Infinity) return null;
            var path = [], u = e; while(u) {{ path.unshift(u); u = prev[u]; }}
            return {{nodes: path, cost: dist[e]}};
        }}

        // --- Display Results & Highlight ---
        function displayPathResults(paths, metric) {{
            var container = document.getElementById('path-results-container');
            container.innerHTML = "";

            if(paths.length === 0) {{
                container.innerHTML =
                  "<div style='color:#e74c3c; padding:10px; text-align:center'>" +
                  "❌ No Path Found</div>";
                return;
            }}

            paths.forEach((p, i) => {{
                var div = document.createElement('div');
                div.className = 'path-item';

                let costText = "";
                if (metric === 'fidelity') {{
                    costText = "Fidelity: " + (Math.exp(-p.cost)*100).toFixed(4) + "%";
                }} else {{
                    costText = "Cost: " + p.cost.toFixed(2);
                }}

                let namePath = p.nodes.map(nid => nodes.get(nid).name).join(" ➝ ");

                // Multiline Template Literal for readability in Python
                div.innerHTML = `
                    <strong>Path ${{i+1}}</strong>
                    <span style="float:right">${{costText}}</span>
                    <div class="path-detail">${{namePath}}</div>
                `;

                div.onclick = function() {{
                    document.querySelectorAll('.path-item').forEach(el =>
                        el.classList.remove('path-active'));
                    div.classList.add('path-active');
                    highlightPath(p.nodes);
                }};

                container.appendChild(div);
            }});

            // Auto-select first path
            if(paths.length > 0) container.children[0].click();
        }}

        function highlightPath(nodesIds) {{
            resetGraphColorOnly();
            // Highlight Edges
            for(let i=0; i<nodesIds.length-1; i++) {{
                let u = nodesIds[i], v = nodesIds[i+1];
                let es = edges.get().filter(e =>
                    (e.from===u && e.to===v) || (e.from===v && e.to===u)
                );
                es.forEach(e => edges.update({{
                    id:e.id,
                    color:{{color: PATH_COLOR}},
                    width: 3
                }}));
            }}
            // Highlight Nodes
            nodesIds.forEach(id => nodes.update({{
                id:id,
                color:{{background: '#ff7675'}}
            }}));
        }}

        function resetGraph() {{
            resetGraphColorOnly();
            network.fit();
            var emptyMsg = "<div style='font-size:12px; color:#aaa; " +
                           "text-align:center; padding:10px;'>" +
                           "Results will appear here</div>";
            document.getElementById('path-results-container').innerHTML = emptyMsg;
            document.querySelectorAll('tr.selected').forEach(r =>
                r.classList.remove('selected'));
        }}

        function resetGraphColorOnly() {{
            edges.update(edges.getIds().map(id => ({{
                id:id,
                color:{{color:'#2B7CE9', highlight: HIGHLIGHT_COLOR}},
                width:1
            }})));

            nodes.update(nodes.getIds().map(id => ({{
                id:id,
                color: {{
                    background:'#97C2FC',
                    border:'#2B7CE9',
                    highlight: {{
                        background: HIGHLIGHT_COLOR,
                        border: HIGHLIGHT_BORDER
                    }}
                }}
            }})));
        }}

        // --- Table Interactions (Toggle) ---
        function attachTableEvents(tableId, isEdge) {{
            var table = document.getElementById(tableId);
            if(!table) return;
            var rows = table.getElementsByTagName('tr');

            for (var i = 1; i < rows.length; i++) {{
                rows[i].onclick = function() {{
                    var wasSelected = this.classList.contains('selected');
                    document.querySelectorAll('tr.selected').forEach(r =>
                        r.classList.remove('selected'));

                    if (wasSelected) {{
                        network.unselectAll();
                        resetGraphColorOnly();
                    }} else {{
                        this.classList.add('selected');
                        if(isEdge) {{
                            var name = this.cells[0].innerText;
                            var target = edges.get().find(e => e.name === name);
                            if(target) network.selectEdges([target.id]);
                        }} else {{
                            var id = parseInt(this.cells[0].innerText);
                            network.selectNodes([id]);
                            network.focus(id, {{ scale: 1.2, animation: true }});
                        }}
                    }}
                }};
            }}
        }}

        attachTableEvents('nodeTable', false);
        attachTableEvents('edgeTable', true);

        // --- UI Utils ---
        function toggleLabels(checkbox) {{
            var show = checkbox.checked;
            nodes.update(nodes.get().map(n =>
                ({{ id: n.id, label: show ? n._realLabel : " " }})
            ));
            edges.update(edges.get().map(e =>
                ({{ id: e.id, label: show ? e._realLabel : " " }})
            ));
        }}

        function togglePhysics(checkbox) {{
            network.setOptions({{ physics: {{ enabled: checkbox.checked }} }});
            if(!checkbox.checked) network.storePositions();
        }}

        function applyColorByName() {{
            var nameInput = document.getElementById('style-name').value.trim();
            var color = document.getElementById('style-color').value;
            var targetNode = nodes.get().find(n => n.name === nameInput);
            if(targetNode) {{
                nodes.update({{
                    id: targetNode.id,
                    color: {{
                        background: color,
                        border: color,
                        highlight:{{
                            background: HIGHLIGHT_COLOR,
                            border: HIGHLIGHT_BORDER
                        }}
                    }}
                }});
                return;
            }}
            alert("Node not found: " + nameInput);
        }}

        function makeResizable(resizer, side) {{
            const l = document.getElementById('left-panel');
            const r = document.getElementById('right-panel');
            const c = document.getElementById('app-container');

            resizer.addEventListener('mousedown', function(e) {{
                e.preventDefault();
                document.addEventListener('mousemove', resize);
                document.addEventListener('mouseup', stopResize);
                function resize(ev) {{
                    if(side==='left') {{
                        l.style.width = Math.max(150, Math.min(500, ev.clientX))+'px';
                    }} else {{
                        let w = c.offsetWidth - ev.clientX;
                        r.style.width = Math.max(150, Math.min(800, w))+'px';
                    }}
                }}
                function stopResize() {{
                    document.removeEventListener('mousemove', resize);
                    document.removeEventListener('mouseup', stopResize);
                }}
            }});
        }}
        makeResizable(document.getElementById('resizer-left'), 'left');
        makeResizable(document.getElementById('resizer-right'), 'right');

        // Modal Logic
        function openModal(id) {{
            document.getElementById(id).style.display = 'block';
        }}
        function closeModal(id) {{
            document.getElementById(id).style.display = 'none';
        }}
        window.onclick = function(event) {{
            if (event.target.classList.contains('modal'))
                event.target.style.display = "none";
        }}

        function addNode() {{
            let id = parseInt(document.getElementById('new-node-id').value);
            let name = document.getElementById('new-node-name').value;
            let apps = document.getElementById('new-node-apps').value;
            if(!id || !name) return alert('ID and Name required');
            nodes.add({{
                id:id,
                label: " ",
                _realLabel: name,
                name: name,
                title: "ID:"+id+" NAME:"+name,
                apps: apps.split(',')
            }});
            closeModal('nodeModal');
        }}

        function addEdge() {{
            let u = parseInt(document.getElementById('new-edge-src').value);
            let v = parseInt(document.getElementById('new-edge-dest').value);
            let bw = parseFloat(document.getElementById('new-edge-bandwidth').value);
            let fid = parseFloat(document.getElementById('new-edge-fidelity').value);
            if(!u || !v) return alert('Source and Dest IDs required');
            edges.add({{
                from:u, to:v, bandwidth: bw, fidelity: fid,
                name: "Link_"+u+"_"+v, title: "Manually Added"
            }});
            closeModal('edgeModal');
        }}
    </script>
    """

    full_html = (
        "<!DOCTYPE html><html><head>"
        "<meta charset='utf-8'><title>Quantum Network Visualizer</title>"
        f"{css_styles}</head><body>{html_structure}{js_logic}</body></html>"
    )

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)

    webbrowser.open('file://' + os.path.realpath(filename))
