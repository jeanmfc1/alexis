"""
Download and build MeSH lookup tables for AACT pipeline.

This script:
1. Downloads official MeSH descriptor and supplementary concept files
2. Parses XML to extract MeSH IDs, terms, and tree numbers
3. Builds lookup dictionaries: term name → MeSH ID → tree codes
4. Saves as JSON for fast loading in AACT pipeline

Output files:
- mesh_descriptors.json: Main MeSH headings with tree numbers
- mesh_supplementary.json: Specific drug/chemical names
- mesh_term_to_id.json: Quick lookup from term name to MeSH ID

Usage:
    python build_mesh_lookup.py [--year 2024]
"""

import argparse
import gzip
import json
import urllib.request
from pathlib import Path
from typing import Dict, List, Set
import xml.etree.ElementTree as ET
from tqdm import tqdm


# MeSH download URLs (NLM official)
MESH_BASE_URL = "https://nlmpubs.nlm.nih.gov/projects/mesh/{year}/xmlmesh"
DESC_FILENAME = "desc{year}.gz"
SUPP_FILENAME = "supp{year}.gz"


def download_file(url: str, output_path: Path, description: str) -> bool:
    """Download file with progress bar."""
    try:
        print(f"\nDownloading: {description}")
        print(f"URL: {url}")
        
        # Get file size
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get('Content-Length', 0))
        
        # Download with progress bar
        with tqdm(total=total_size, unit='B', unit_scale=True, desc=description) as pbar:
            def update_progress(block_num, block_size, total_size):
                pbar.update(block_size)
            
            urllib.request.urlretrieve(url, output_path, reporthook=update_progress)
        
        print(f"✓ Downloaded: {output_path.name} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
        return True
        
    except Exception as e:
        print(f"✗ Download failed: {e}")
        return False


def parse_descriptors(desc_file: Path) -> Dict:
    """
    Parse MeSH descriptors XML.
    
    Returns dict: {
        'D000001': {
            'name': 'Calcimycin',
            'tree_numbers': ['D03.438.221.173'],
            'terms': ['Calcimycin', 'A-23187', 'A23187', ...]
        }
    }
    """
    print(f"\nParsing descriptors: {desc_file.name}")
    
    descriptors = {}
    
    # Decompress and parse
    with gzip.open(desc_file, 'rt', encoding='utf-8') as f:
        tree = ET.parse(f)
        root = tree.getroot()
        
        descriptor_records = root.findall('.//DescriptorRecord')
        print(f"  Found {len(descriptor_records):,} descriptor records")
        
        for record in tqdm(descriptor_records, desc="  Processing descriptors"):
            # Get descriptor UI (ID)
            ui_elem = record.find('DescriptorUI')
            if ui_elem is None:
                continue
            descriptor_id = ui_elem.text
            
            # Get descriptor name
            name_elem = record.find('.//DescriptorName/String')
            if name_elem is None:
                continue
            descriptor_name = name_elem.text
            
            # Get all tree numbers
            tree_numbers = []
            for tn in record.findall('.//TreeNumber'):
                if tn.text:
                    tree_numbers.append(tn.text)
            
            # Get all terms (entry terms, synonyms)
            terms = {descriptor_name}  # Start with main name
            
            # Add concepts
            for concept in record.findall('.//Concept'):
                # Preferred term
                pref_term = concept.find('.//ConceptName/String')
                if pref_term is not None and pref_term.text:
                    terms.add(pref_term.text)
                
                # Entry terms (synonyms)
                for term_elem in concept.findall('.//Term/String'):
                    if term_elem.text:
                        terms.add(term_elem.text)
            
            descriptors[descriptor_id] = {
                'name': descriptor_name,
                'tree_numbers': tree_numbers,
                'terms': sorted(list(terms))
            }
    
    print(f"  ✓ Parsed {len(descriptors):,} descriptors")
    return descriptors


def parse_supplementary(supp_file: Path) -> Dict:
    """
    Parse MeSH supplementary concept records (SCRs).
    
    These are specific drugs/chemicals mapped to broader descriptors.
    
    Returns dict: {
        'C000001': {
            'name': 'Bevacizumab',
            'mapped_to': ['D000074322'],  # Maps to descriptor IDs
            'terms': ['Bevacizumab', 'Avastin', ...]
        }
    }
    """
    print(f"\nParsing supplementary concepts: {supp_file.name}")
    
    supplementary = {}
    
    with gzip.open(supp_file, 'rt', encoding='utf-8') as f:
        tree = ET.parse(f)
        root = tree.getroot()
        
        supp_records = root.findall('.//SupplementalRecord')
        print(f"  Found {len(supp_records):,} supplementary records")
        
        for record in tqdm(supp_records, desc="  Processing supplements"):
            # Get SCR ID
            ui_elem = record.find('SupplementalRecordUI')
            if ui_elem is None:
                continue
            scr_id = ui_elem.text
            
            # Get name
            name_elem = record.find('.//SupplementalRecordName/String')
            if name_elem is None:
                continue
            scr_name = name_elem.text
            
            # Get mapped descriptors (headings this SCR maps to)
            mapped_to = []
            for heading in record.findall('.//HeadingMappedTo/DescriptorReferredTo/DescriptorUI'):
                if heading.text:
                    mapped_to.append(heading.text)
            
            # Get all terms
            terms = {scr_name}
            
            for concept in record.findall('.//Concept'):
                # Preferred term
                pref_term = concept.find('.//ConceptName/String')
                if pref_term is not None and pref_term.text:
                    terms.add(pref_term.text)
                
                # Entry terms
                for term_elem in concept.findall('.//Term/String'):
                    if term_elem.text:
                        terms.add(term_elem.text)
            
            supplementary[scr_id] = {
                'name': scr_name,
                'mapped_to': mapped_to,
                'terms': sorted(list(terms))
            }
    
    print(f"  ✓ Parsed {len(supplementary):,} supplementary concepts")
    return supplementary


def build_term_to_id_lookup(descriptors: Dict, supplementary: Dict) -> Dict[str, str]:
    """
    Build fast lookup: term name → MeSH ID.
    
    Handles case-insensitive matching and multiple synonyms.
    """
    print("\nBuilding term → ID lookup...")
    
    term_to_id = {}
    
    # Add descriptors
    for desc_id, desc_data in descriptors.items():
        for term in desc_data['terms']:
            # Store lowercase for case-insensitive lookup
            term_lower = term.lower()
            if term_lower not in term_to_id:
                term_to_id[term_lower] = desc_id
    
    # Add supplementary (these take precedence for specific drug names)
    for scr_id, scr_data in supplementary.items():
        for term in scr_data['terms']:
            term_lower = term.lower()
            # SCRs override descriptors (more specific)
            term_to_id[term_lower] = scr_id
    
    print(f"  ✓ Built lookup with {len(term_to_id):,} terms")
    return term_to_id


def get_tree_numbers_for_term(
    term: str,
    term_to_id: Dict[str, str],
    descriptors: Dict,
    supplementary: Dict
) -> List[str]:
    """
    Get MeSH tree numbers for a term name.
    
    Returns list of tree numbers, or empty list if not found.
    """
    term_lower = term.lower()
    mesh_id = term_to_id.get(term_lower)
    
    if not mesh_id:
        return []
    
    # Direct descriptor
    if mesh_id in descriptors:
        return descriptors[mesh_id]['tree_numbers']
    
    # Supplementary concept - get tree numbers from mapped descriptors
    if mesh_id in supplementary:
        tree_numbers = []
        for mapped_id in supplementary[mesh_id]['mapped_to']:
            if mapped_id in descriptors:
                tree_numbers.extend(descriptors[mapped_id]['tree_numbers'])
        return tree_numbers
    
    return []


def main():
    parser = argparse.ArgumentParser(description='Build MeSH lookup tables')
    parser.add_argument('--year', type=int, default=2024, help='MeSH year version')
    parser.add_argument('--output-dir', type=Path, default=Path('storage/mesh'),
                       help='Output directory for JSON files')
    args = parser.parse_args()
    
    print("="*70)
    print("MeSH Lookup Builder")
    print("="*70)
    print(f"\nMeSH Year: {args.year}")
    print(f"Output directory: {args.output_dir}")
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download paths
    download_dir = args.output_dir / "downloads"
    download_dir.mkdir(exist_ok=True)
    
    desc_file = download_dir / DESC_FILENAME.format(year=args.year)
    supp_file = download_dir / SUPP_FILENAME.format(year=args.year)
    
    # Download files
    desc_url = f"{MESH_BASE_URL.format(year=args.year)}/{DESC_FILENAME.format(year=args.year)}"
    supp_url = f"{MESH_BASE_URL.format(year=args.year)}/{SUPP_FILENAME.format(year=args.year)}"
    
    if not desc_file.exists():
        if not download_file(desc_url, desc_file, "MeSH Descriptors"):
            print("\n✗ Failed to download descriptors")
            return
    else:
        print(f"\n✓ Using cached: {desc_file.name}")
    
    if not supp_file.exists():
        if not download_file(supp_url, supp_file, "MeSH Supplementary"):
            print("\n✗ Failed to download supplementary concepts")
            return
    else:
        print(f"\n✓ Using cached: {supp_file.name}")
    
    # Parse files
    descriptors = parse_descriptors(desc_file)
    supplementary = parse_supplementary(supp_file)
    
    # Build lookup
    term_to_id = build_term_to_id_lookup(descriptors, supplementary)
    
    # Save JSON files
    print("\nSaving lookup tables...")
    
    desc_output = args.output_dir / "mesh_descriptors.json"
    with open(desc_output, 'w') as f:
        json.dump(descriptors, f, indent=2)
    print(f"  ✓ Saved: {desc_output.name} ({desc_output.stat().st_size / 1024 / 1024:.1f} MB)")
    
    supp_output = args.output_dir / "mesh_supplementary.json"
    with open(supp_output, 'w') as f:
        json.dump(supplementary, f, indent=2)
    print(f"  ✓ Saved: {supp_output.name} ({supp_output.stat().st_size / 1024 / 1024:.1f} MB)")
    
    term_output = args.output_dir / "mesh_term_to_id.json"
    with open(term_output, 'w') as f:
        json.dump(term_to_id, f, indent=2)
    print(f"  ✓ Saved: {term_output.name} ({term_output.stat().st_size / 1024 / 1024:.1f} MB)")
    
    # Test examples
    print("\n" + "="*70)
    print("Testing lookup with examples:")
    print("="*70)
    
    test_terms = [
        "Bevacizumab",
        "Aspirin",
        "Glucose",
        "Neoplasms",
        "Diabetes Mellitus"
    ]
    
    for term in test_terms:
        tree_nums = get_tree_numbers_for_term(term, term_to_id, descriptors, supplementary)
        mesh_id = term_to_id.get(term.lower(), "NOT FOUND")
        
        is_drug = any(tn.startswith('D') for tn in tree_nums)
        
        print(f"\n{term}:")
        print(f"  MeSH ID: {mesh_id}")
        print(f"  Tree numbers: {tree_nums[:3]}{'...' if len(tree_nums) > 3 else ''}")
        print(f"  Is drug/chemical: {is_drug}")
    
    print("\n" + "="*70)
    print("✓ MeSH lookup tables built successfully!")
    print("="*70)
    print(f"\nFiles saved to: {args.output_dir}")
    print("\nNext steps:")
    print("  1. Use mesh_term_to_id.json for fast lookups")
    print("  2. Use mesh_descriptors.json for tree number resolution")
    print("  3. Integrate into AACT pipeline for drug detection")


if __name__ == '__main__':
    main()
