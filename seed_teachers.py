"""
Seed teacher profiles from a CSV file.

Usage:
    python seed_teachers.py teachers.csv
    python seed_teachers.py --example    # print a sample CSV and exit
"""

import argparse
import csv
import logging
import sys

from pipeline.config import CONFIG
from pipeline.database import DatabaseManager, get_db_connection

EXAMPLE_CSV = """\
email,first_name,last_name,discipline,grade_band,years_experience,current_module,tailoring_query,discipline_key
jane.doe@paceacademy.org,Jane,Doe,AP Chemistry,9-12,12,Thermodynamics,I want to improve inquiry-based lab design and help advanced students connect chemistry to real-world applications,us_science
mark.chen@paceacademy.org,Mark,Chen,7th Grade English,6-8,3,Narrative Writing,I struggle with keeping students engaged during the drafting phase and want better peer-editing strategies,ms_english
sarah.james@paceacademy.org,Sarah,James,Elementary Math,K-5,7,Fractions,I want differentiation strategies for a wide ability range in the same classroom,ls_math
novice-math@paceacademy.org,Jordan,Rivera,6th Grade Math,6-8,2,Fractions and Ratios,I struggle with engagement during independent practice and supporting struggling learners without slowing the class,ms_math
"""

def main():
    parser = argparse.ArgumentParser(description="Seed teacher profiles from CSV")
    parser.add_argument("csv_file", nargs="?", help="Path to teachers CSV file")
    parser.add_argument("--example", action="store_true", help="Print example CSV and exit")
    args = parser.parse_args()

    if args.example:
        print(EXAMPLE_CSV)
        sys.exit(0)

    if not args.csv_file:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    conn = get_db_connection(CONFIG.DATABASE_URL)
    db   = DatabaseManager(conn)
    db.create_tables()

    inserted, updated = 0, 0
    with open(args.csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize keys: strip whitespace
            profile = {k.strip(): v.strip() for k, v in row.items()}
            if not profile.get('email') or not profile.get('discipline'):
                logging.warning(f"Skipping row with missing email or discipline: {profile}")
                continue
            db.upsert_teacher(profile)
            logging.info(f"  Upserted: {profile['email']}")
            inserted += 1

    conn.close()
    logging.info(f"Done. {inserted} teacher profiles written.")

if __name__ == "__main__":
    main()
