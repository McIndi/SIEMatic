import os

def indexer_mode(request):
    """
    Context processor to add indexer mode flag to all templates.
    """
    return {
        'is_indexer_mode': os.getenv('INDEXER_MODE') == '1',
    }