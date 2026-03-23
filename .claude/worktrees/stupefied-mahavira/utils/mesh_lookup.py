"""
MeSH lookup utilities for AACT pipeline.

Provides fast lookup from MeSH term names to tree numbers,
enabling accurate drug/chemical classification.

Usage:
    from utils.mesh_lookup import MeshLookup
    
    mesh = MeshLookup()
    tree_numbers = mesh.get_tree_numbers("Bevacizumab")
    # Returns: ['D12.776.124.486.485.114']
    
    is_drug = mesh.is_drug_or_chemical("Aspirin")
    # Returns: True (tree numbers start with 'D')
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set


class MeshLookup:
    """Fast MeSH term → tree number lookup."""
    
    def __init__(self, mesh_dir: Optional[Path] = None):
        """
        Initialize MeSH lookup.
        
        Args:
            mesh_dir: Path to directory with mesh_*.json files.
                     If None, uses storage/mesh/
        """
        if mesh_dir is None:
            # Default to storage/mesh in project root
            mesh_dir = Path(__file__).parent.parent / "storage" / "mesh"
        
        self.mesh_dir = Path(mesh_dir)
        
        # Lookup tables
        self.term_to_id: Dict[str, str] = {}
        self.descriptors: Dict = {}
        self.supplementary: Dict = {}
        
        # Load if files exist
        self._load_lookup_tables()
    
    def _load_lookup_tables(self):
        """Load MeSH lookup tables from JSON files."""
        term_file = self.mesh_dir / "mesh_term_to_id.json"
        desc_file = self.mesh_dir / "mesh_descriptors.json"
        supp_file = self.mesh_dir / "mesh_supplementary.json"
        
        if not term_file.exists():
            print(f"⚠ MeSH lookup not initialized. Run: python build_mesh_lookup.py")
            print(f"  Expected file: {term_file}")
            return
        
        # Load term → ID mapping
        with open(term_file, 'r') as f:
            self.term_to_id = json.load(f)
        
        # Load descriptors
        with open(desc_file, 'r') as f:
            self.descriptors = json.load(f)
        
        # Load supplementary concepts
        with open(supp_file, 'r') as f:
            self.supplementary = json.load(f)
        
        print(f"✓ Loaded MeSH lookup: {len(self.term_to_id):,} terms")
    
    def is_loaded(self) -> bool:
        """Check if MeSH lookup tables are loaded."""
        return bool(self.term_to_id)
    
    def get_mesh_id(self, term: str) -> Optional[str]:
        """
        Get MeSH ID for a term name.
        
        Args:
            term: MeSH term name (case-insensitive)
        
        Returns:
            MeSH ID (e.g., 'D000001') or None if not found
        """
        return self.term_to_id.get(term.lower())
    
    def get_tree_numbers(self, term: str) -> List[str]:
        """
        Get MeSH tree numbers for a term.
        
        Args:
            term: MeSH term name (case-insensitive)
        
        Returns:
            List of tree numbers (e.g., ['D03.438.221.173'])
            Empty list if term not found
        """
        mesh_id = self.get_mesh_id(term)
        if not mesh_id:
            return []
        
        # Direct descriptor
        if mesh_id in self.descriptors:
            return self.descriptors[mesh_id]['tree_numbers']
        
        # Supplementary concept - resolve through mapped descriptors
        if mesh_id in self.supplementary:
            tree_numbers = []
            for mapped_id in self.supplementary[mesh_id]['mapped_to']:
                if mapped_id in self.descriptors:
                    tree_numbers.extend(self.descriptors[mapped_id]['tree_numbers'])
            return tree_numbers
        
        return []
    
    def is_drug_or_chemical(self, term: str) -> bool:
        """
        Check if a MeSH term is a drug or chemical.
        
        Args:
            term: MeSH term name
        
        Returns:
            True if any tree number starts with 'D' (Chemicals and Drugs category)
        """
        tree_numbers = self.get_tree_numbers(term)
        return any(tn.startswith('D') for tn in tree_numbers)
    
    def get_tree_ancestors(self, tree_number: str) -> List[str]:
        """
        Get all ancestors of a tree number.
        
        Example:
            'D03.438.221.173' → ['D03', 'D03.438', 'D03.438.221', 'D03.438.221.173']
        
        Args:
            tree_number: MeSH tree number
        
        Returns:
            List of ancestor tree numbers (including self)
        """
        parts = tree_number.split('.')
        ancestors = []
        
        for i in range(1, len(parts) + 1):
            ancestors.append('.'.join(parts[:i]))
        
        return ancestors
    
    def get_all_tree_ancestors(self, term: str) -> List[str]:
        """
        Get all tree ancestors for all tree numbers of a term.
        
        Args:
            term: MeSH term name
        
        Returns:
            List of all ancestor tree numbers (deduplicated)
        """
        tree_numbers = self.get_tree_numbers(term)
        
        all_ancestors = set()
        for tn in tree_numbers:
            all_ancestors.update(self.get_tree_ancestors(tn))
        
        return sorted(list(all_ancestors))
    
    def get_primary_tree_category(self, term: str) -> Optional[str]:
        """
        Get primary MeSH tree category letter for a term.
        
        Categories:
            A - Anatomy
            B - Organisms
            C - Diseases
            D - Chemicals and Drugs
            E - Analytical/Diagnostic Techniques
            F - Psychiatry and Psychology
            G - Phenomena and Processes
            ...
        
        Args:
            term: MeSH term name
        
        Returns:
            Category letter (e.g., 'D') or None
        """
        tree_numbers = self.get_tree_numbers(term)
        if not tree_numbers:
            return None
        
        # Return first category
        return tree_numbers[0][0]


# Global instance (lazy loading)
_mesh_lookup: Optional[MeshLookup] = None

def get_mesh_lookup() -> MeshLookup:
    """Get global MeshLookup instance (singleton pattern)."""
    global _mesh_lookup
    if _mesh_lookup is None:
        _mesh_lookup = MeshLookup()
    return _mesh_lookup


def enrich_mesh_terms_with_tree_numbers(
    mesh_terms: List[str],
    mesh_lookup: Optional[MeshLookup] = None
) -> List[Dict]:
    """
    Enrich list of MeSH term names with tree numbers.
    
    Args:
        mesh_terms: List of MeSH term names
        mesh_lookup: MeshLookup instance (uses global if None)
    
    Returns:
        List of dicts with 'term', 'id', 'tree_numbers', 'ancestors'
    """
    if mesh_lookup is None:
        mesh_lookup = get_mesh_lookup()
    
    if not mesh_lookup.is_loaded():
        # MeSH not available, return minimal structure
        return [{'term': term, 'id': None, 'tree_numbers': [], 'ancestors': []} 
                for term in mesh_terms]
    
    enriched = []
    for term in mesh_terms:
        mesh_id = mesh_lookup.get_mesh_id(term)
        tree_numbers = mesh_lookup.get_tree_numbers(term)
        ancestors = mesh_lookup.get_all_tree_ancestors(term)
        
        enriched.append({
            'term': term,
            'id': mesh_id,
            'tree_numbers': tree_numbers,
            'ancestors': ancestors
        })
    
    return enriched


if __name__ == '__main__':
    # Test the lookup
    mesh = MeshLookup()
    
    if not mesh.is_loaded():
        print("MeSH lookup not initialized.")
        print("Run: python build_mesh_lookup.py")
    else:
        test_terms = [
            "Bevacizumab",
            "Aspirin", 
            "Glucose",
            "Neoplasms",
            "Diabetes Mellitus"
        ]
        
        print("Testing MeSH Lookup:")
        print("="*60)
        
        for term in test_terms:
            mesh_id = mesh.get_mesh_id(term)
            tree_nums = mesh.get_tree_numbers(term)
            is_drug = mesh.is_drug_or_chemical(term)
            category = mesh.get_primary_tree_category(term)
            
            print(f"\n{term}:")
            print(f"  ID: {mesh_id}")
            print(f"  Trees: {tree_nums[:2]}{'...' if len(tree_nums) > 2 else ''}")
            print(f"  Category: {category}")
            print(f"  Is drug: {is_drug}")
