import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
load_dotenv()
url = os.getenv('DATABASE_URL')
if url.startswith('postgresql://'):
    url = 'postgresql+psycopg://' + url.removeprefix('postgresql://')
engine = create_engine(url)
with engine.connect() as conn:
    result = conn.execute(text("SELECT verdict, COUNT(*) FROM stock_scores GROUP BY verdict"))
    for row in result:
        print(row)