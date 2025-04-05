import argparse
import csv

def convert_kicad_to_jlcpcb(input_file: str):
    # Define column name mappings
    column_mapping = {
        "Ref": "Designator",
        "PosX": "Mid X",
        "PosY": "Mid Y",
        "Rot": "Rotation",
        "Side": "Layer"
    }
    
    # Read the CSV file
    with open(input_file, newline='') as infile:
        reader = csv.DictReader(infile)
        rows = [row for row in reader]
        
    # Rename columns
    new_fieldnames = [column_mapping.get(field, field) for field in reader.fieldnames]
    for row in rows:
        for old_col, new_col in column_mapping.items():
            if old_col in row:
                row[new_col] = row.pop(old_col)
    
    # Write the updated CSV file, overwriting the original
    with open(input_file, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Converted file saved as {input_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert KiCad position file to JLCPCB format.")
    parser.add_argument("input", help="Path to the KiCad position CSV file")
    args = parser.parse_args()
    
    convert_kicad_to_jlcpcb(args.input)
