import os
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from langchain_community.vectorstores import Chroma
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain.prompts import FewShotPromptTemplate, SemanticSimilarityExampleSelector
from langchain.prompts import PromptTemplate
from langchain.chains.sql_database.prompt import PROMPT_SUFFIX
from langchain_together import Together
from few_shots import few_shots

# Load environment variables
load_dotenv()

# PostgreSQL credentials
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", 5432)

# LLM and Embedding models
LLM_MODEL = "mistralai/Mistral-7B-Instruct-v0.1"
EMBEDDINGS_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Connect to PostgreSQL
try:
    db = SQLDatabase.from_uri(
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        sample_rows_in_table_info=3
    )
    print("✅ PostgreSQL database connected successfully!")
except Exception as e:
    print(f"❌ Database connection error: {e}")
    db = None

# Initialize LLM
llm = Together(
    model=LLM_MODEL,
    temperature=0.2,
    max_tokens=500,
    together_api_key=os.getenv("TOGETHER_API_KEY"),
)

# Setup embeddings
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDINGS_MODEL)

# Prepare vector texts from few-shot examples
vector_texts = [" ".join(str(value) for value in example.values()) for example in few_shots]

# Initialize Chroma vectorstore
vectorstore = Chroma.from_texts(
    texts=vector_texts,
    embedding=embeddings,
    metadatas=few_shots,
    persist_directory=".chroma"
)
vectorstore.persist()
print("✅ Chroma Vectorstore Initialized and Persisted")

# Example selector for few-shot
example_selector = SemanticSimilarityExampleSelector(
    vectorstore=vectorstore,
    k=2
)

# PostgreSQL-specific prompt with schema logic
postgres_prompt = """You are a PostgreSQL expert. Given an input question, write a syntactically correct SQL query to run, then return the result.

Instructions:
- Never use SELECT *.
- Use only necessary columns.
- Use LIMIT {top_k} where applicable.
- Avoid filtering by `report_date` unless the question explicitly mentions a date or time frame (e.g., "today", "last week", "on April 1st").

Schema relationships:
- Most tables reference `plant_id`, but the plant name is in the `plants` table. To filter by plant name, JOIN the target table with `plants` using `target_table.plant_id = plants.plant_id`.
- Similarly, most mill-level tables only have `mill_id`, and the mill name is in the `mills` table. JOIN using `target_table.mill_id = mills.mill_id`.
- Always infer joins based on whether plant_name or mill_name is referenced in the question.

Do not use aliases unless necessary. Focus on correctness and clarity."""

# Prompt templates
example_prompt = PromptTemplate(
    input_variables=["Question", "SQLQuery", "SQLResult", "Answer"],
    template="\nQuestion: {Question}\nSQLQuery: {SQLQuery}\nSQLResult: {SQLResult}\nAnswer: {Answer}",
)

few_shot_prompt = FewShotPromptTemplate(
    example_selector=example_selector,
    example_prompt=example_prompt,
    prefix=postgres_prompt,
    suffix=PROMPT_SUFFIX,
    input_variables=["input", "table_info", "top_k"],
)

# Reset session placeholder (optional)
def reset_session_state():
    print("✅ Resetting session state...")

# Get a fresh SQLDatabaseChain each time
def get_few_shot_db_chain():
    try:
        reset_session_state()
        chain = SQLDatabaseChain.from_llm(
            llm=llm,
            db=db,
            verbose=False,
            prompt=few_shot_prompt,
            use_query_checker=True,
            return_intermediate_steps=False
        )
        print("✅ SQLDatabaseChain initialized successfully!")
        return chain
    except Exception as e:
        print(f"❌ Error initializing SQLDatabaseChain: {e}")
        return None

# Public function used by FastAPI to process incoming queries
def process_query(query):
    print(f"🔍 Processing query: {query}")
    result = "Unable to process the query."
    chain = get_few_shot_db_chain()
    if chain:
        try:
            response = chain.invoke({"query": query})
            result = response.get("result", "No result returned.")
            if isinstance(result, dict):
                result = str(result)
            print(f"✅ Answer: {result}")
        except Exception as e:
            result = f"❌ Error processing your question. Details: {e}"
            print(result)
    else:
        result = "❌ Failed to initialize the chain."
    reset_session_state()
    return result
