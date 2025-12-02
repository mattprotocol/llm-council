#!/usr/bin/env python3
"""
Script to remove all Hermes-related nodes and edges from the Graphiti knowledge graph.
This cleans up incorrect AI name associations by directly accessing FalkorDB.
"""

import sys


def remove_hermes_nodes():
    """Remove all nodes and edges related to 'hermes' from the graph using direct FalkorDB access."""
    
    try:
        from falkordb import FalkorDB
    except ImportError:
        print("ERROR: falkordb package not installed. Run: pip install falkordb")
        return False
    
    print("Connecting to FalkorDB...")
    db = FalkorDB(host='localhost', port=6379)
    
    # Get all graphs
    graphs = db.list_graphs()
    print(f"Found graphs: {graphs}")
    
    total_deleted_nodes = 0
    total_deleted_edges = 0
    
    for graph_name in graphs:
        print(f"\n=== Processing graph: {graph_name} ===")
        graph = db.select_graph(graph_name)
        
        # Find nodes containing 'hermes' in name or summary
        try:
            result = graph.query("""
                MATCH (n) 
                WHERE toLower(toString(n.name)) CONTAINS 'hermes' 
                   OR toLower(toString(n.summary)) CONTAINS 'hermes'
                   OR toLower(toString(n.content)) CONTAINS 'hermes'
                RETURN n.uuid, n.name, n.summary
            """)
            
            hermes_nodes = []
            if result.result_set:
                for row in result.result_set:
                    uuid, name, summary = row[0], row[1], row[2]
                    hermes_nodes.append(uuid)
                    print(f"  Found node: {name} - {str(summary)[:50]}...")
            
            if hermes_nodes:
                # Delete edges connected to hermes nodes first
                edge_result = graph.query("""
                    MATCH (n)-[r]-()
                    WHERE toLower(toString(n.name)) CONTAINS 'hermes' 
                       OR toLower(toString(n.summary)) CONTAINS 'hermes'
                       OR toLower(toString(n.content)) CONTAINS 'hermes'
                    DELETE r
                    RETURN count(r) as deleted_edges
                """)
                deleted_edges = edge_result.result_set[0][0] if edge_result.result_set else 0
                print(f"  Deleted {deleted_edges} edges connected to Hermes nodes")
                total_deleted_edges += deleted_edges
                
                # Delete the hermes nodes
                node_result = graph.query("""
                    MATCH (n) 
                    WHERE toLower(toString(n.name)) CONTAINS 'hermes' 
                       OR toLower(toString(n.summary)) CONTAINS 'hermes'
                       OR toLower(toString(n.content)) CONTAINS 'hermes'
                    DELETE n
                    RETURN count(n) as deleted_nodes
                """)
                deleted_nodes = node_result.result_set[0][0] if node_result.result_set else 0
                print(f"  Deleted {deleted_nodes} Hermes nodes")
                total_deleted_nodes += deleted_nodes
            else:
                print(f"  No Hermes nodes found in {graph_name}")
                
        except Exception as e:
            print(f"  Error processing {graph_name}: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Total nodes deleted: {total_deleted_nodes}")
    print(f"Total edges deleted: {total_deleted_edges}")
    
    return True


if __name__ == "__main__":
    success = remove_hermes_nodes()
    sys.exit(0 if success else 1)
