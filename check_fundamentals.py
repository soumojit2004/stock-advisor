import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
load_dotenv()
url = os.getenv('DATABASE_URL')
if url.startswith('postgresql://'):
    url = 'postgresql+psycopg://' + url.removeprefix('postgresql://')
engine = create_engine(url)
with engine.connect() as conn:
    result = conn.execute(text("SELECT MAX(fetched_at) FROM fundamentals"))
    print('Last fundamentals update:', result.fetchone()[0])