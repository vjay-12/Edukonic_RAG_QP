"""
Clean section headings in the database and chunker.
Drops 'CHAPTER11 Electricity', sentence fragments, and associates activities with canonical NCERT section titles.
"""
import sys
from pathlib import Path

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Chunk

def clean_headings():
    db = SessionLocal()
    try:
        updates = {
            490: "1.1 Chemical Equations (Introduction)",
            507: "1.2.4 Double Displacement Reaction (Activity 1.9)",
            518: "1.3.1 Corrosion & Rancidity (Activity)",
            519: "5.1 What are Life Processes?",
            561: "11.1 Electric Current and Circuit (Introduction)",
            569: "11.4 Ohm's Law (Activity 11.1)",
            570: "11.4 Ohm's Law (V-I Relationship)",
            571: "11.4 Ohm's Law (Resistance and Rheostat)",
            572: "11.4 Ohm's Law (Activity 11.2 - Component Resistance)",
            573: "11.5 Factors on which Resistance of a Conductor Depends (Activity 11.3)",
            574: "11.5 Factors on which Resistance of a Conductor Depends (Resistivity)",
            575: "11.5 Factors on which Resistance of a Conductor Depends (Table 11.2)",
            582: "11.6.1 Resistors in Series (Activity 11.4)",
            583: "11.6.1 Resistors in Series (Activity 11.5)",
            584: "11.6.1 Resistors in Series (Potential Difference Division)",
            586: "11.6.2 Resistors in Parallel",
            587: "11.6.2 Resistors in Parallel (Activity 11.6)",
            588: "11.6.2 Resistors in Parallel (Current Division)",
            594: "11.7.1 Joule's Law of Heating",
        }

        updated_count = 0
        for cid, new_hd in updates.items():
            c = db.query(Chunk).filter(Chunk.id == cid).first()
            if c and c.section_heading != new_hd:
                print(f"Chunk {cid}: {repr(c.section_heading)} -> {repr(new_hd)}")
                c.section_heading = new_hd
                updated_count += 1

        db.commit()
        print(f"Successfully cleaned {updated_count} chunk section headings in database.")
    finally:
        db.close()

if __name__ == "__main__":
    clean_headings()
