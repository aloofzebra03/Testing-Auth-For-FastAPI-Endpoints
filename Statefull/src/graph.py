from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.postgres import PostgresSaver
from .models import JokeState
from .core import generate_joke, generate_explanation
# import sqlite3
from psycopg_pool import ConnectionPool
import os

# Database file for persistent storage
DB_PATH = "checkpoints.db"

def create_workflow():
    print("Setting up stateful joke generation workflow")
    
    # Create the state graph
    graph = StateGraph(JokeState)
    
    # Add nodes
    graph.add_node('generate_joke', generate_joke)
    graph.add_node('generate_explanation', generate_explanation)
    
    # Add edges
    graph.add_edge(START, 'generate_joke')
    graph.add_edge('generate_joke', 'generate_explanation')
    graph.add_edge('generate_explanation', END)
    
    # Create SQLite connection and checkpointer
    # SqliteSaver needs to be created with a connection
    # conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # checkpointer = SqliteSaver(conn)
    
    # print("SQLite checkpointer initialized",checkpointer)
    # Compile the workflow with interrupt AFTER joke generation

    # PostgresSaver requires psycopg3 connection pool
    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": None,
    }
    pool = ConnectionPool(
        conninfo=os.getenv('POSTGRES_DATABASE_URL'),
        max_size=20,
        kwargs=connection_kwargs,
    )
    checkpointer = PostgresSaver(pool)
    # checkpointer.setup()  # Create tables if they don't exist
    print("Postgres checkpointer initialized", checkpointer)
    
    workflow = graph.compile(
        checkpointer=checkpointer,
        interrupt_after=['generate_joke']
    )
    print("Workflow setup completed with PostgreSQL persistence")
    
    return workflow
# Create global workflow instance
workflow = create_workflow()

def start_joke_generation(topic: str, thread_id: str):
    try:
        config = {"configurable": {"thread_id": thread_id}}
        print(f"Starting joke generation for topic: {topic}, thread: {thread_id}")
        
        # Initial state
        initial_state = {
            'topic': topic,
            'joke': None,
            'explanation': None,
            'status': 'started'
        }
        
        result = workflow.invoke(initial_state, config=config)
        print(f"Joke generation completed for thread: {thread_id}")
        
        return {
            'topic': result.get('topic'),
            'joke': result.get('joke'),
            'status': result.get('status', 'joke_generated'),
            'thread_id': thread_id
        }
    except Exception as e:
        print(f"Error in start_joke_generation: {str(e)}")
        raise


def continue_with_explanation(thread_id: str):
    try:
        config = {"configurable": {"thread_id": thread_id}}
        print(f"Continuing workflow for thread: {thread_id}")
        
        # Get current state to verify it exists
        current_state = workflow.get_state(config)
        
        if not current_state or not current_state.values:
            raise ValueError(f"No active workflow found for thread_id: {thread_id}")
        
        # Check if joke exists
        if not current_state.values.get('joke'):
            raise ValueError(f"No joke found for thread_id: {thread_id}. Start workflow first.")
        
        # Continue from where we left off (None means continue with no new input)
        result = workflow.invoke(None, config=config)
        print(f"Explanation generated for thread: {thread_id}")
        
        return {
            'topic': result.get('topic'),
            'joke': result.get('joke'),
            'explanation': result.get('explanation'),
            'status': result.get('status', 'completed'),
            'thread_id': thread_id
        }
    except Exception as e:
        print(f"Error in continue_with_explanation: {str(e)}")
        raise


def get_thread_status(thread_id: str):
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = workflow.get_state(config)
        
        if not state or not state.values:
            return {
                'exists': False,
                'message': f"No workflow found for thread_id: {thread_id}"
            }
        
        return {
            'exists': True,
            'thread_id': thread_id,
            'status': state.values.get('status', 'unknown'),
            'topic': state.values.get('topic'),
            'has_joke': bool(state.values.get('joke')),
            'has_explanation': bool(state.values.get('explanation')),
            'next_node': state.next[0] if state.next else None
        }
    except Exception as e:
        print(f"Error in get_thread_status: {str(e)}")
        raise
