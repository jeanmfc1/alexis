from multiprocessing import Pool, cpu_count
from typing import List, Callable, Any, Optional
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)


def get_optimal_worker_count(num_trials: int, min_batch_size: int = 100) -> int:
    """
    Determine optimal number of worker processes.
    
    Args:
        num_trials: Total number of trials to process
        min_batch_size: Minimum trials per worker (avoid overhead for tiny batches)
    
    Returns:
        Number of worker processes to use
    """
    max_workers = cpu_count() - 1  # Leave 1 core free for OS
    max_workers = max(1, max_workers)  # At least 1 worker
    
    # Don't create more workers than we can efficiently use
    efficient_workers = num_trials // min_batch_size
    
    return min(max_workers, efficient_workers)


def chunk_list(items: List[Any], num_chunks: int) -> List[List[Any]]:
    """
    Split a list into roughly equal chunks.
    
    Args:
        items: List to split
        num_chunks: Number of chunks to create
    
    Returns:
        List of chunks
    """
    chunk_size = len(items) // num_chunks
    remainder = len(items) % num_chunks
    
    chunks = []
    start = 0
    
    for i in range(num_chunks):
        # Distribute remainder across first chunks
        extra = 1 if i < remainder else 0
        end = start + chunk_size + extra
        chunks.append(items[start:end])
        start = end
    
    return chunks


def classify_trial_batch(args: tuple) -> List[Any]:
    """
    Worker function: Classify a batch of trials.
    
    This runs in a separate process, so it needs all data passed as arguments.
    Cannot use global state or shared objects.
    
    Args:
        args: Tuple of (trials_batch, classifier_function, batch_id, total_batches)
            - trials_batch: List of ClinicalTrialSignalV2 objects
            - classifier_function: Function that classifies a single trial
            - batch_id: ID of this batch (for progress reporting)
            - total_batches: Total number of batches
    
    Returns:
        List of classified trial objects
    """
    trials_batch, classifier_function, batch_id, total_batches = args
    
    classified_trials = []
    
    for trial in trials_batch:
        try:
            # Call the classifier function on each trial
            classified_trial = classifier_function(trial)
            classified_trials.append(classified_trial)
        except Exception as e:
            logger.error(f"Error classifying trial {trial.nct_id}: {e}")
            # Still append the trial even if classification fails
            classified_trials.append(trial)
    
    return classified_trials


def process_trials_parallel(
    trials: List[Any],
    classifier_function: Callable,
    num_workers: Optional[int] = None
) -> List[Any]:
    """
    Process trials in parallel using multiprocessing with progress bar.
    
    Args:
        trials: List of ClinicalTrialSignalV2 objects to classify
        classifier_function: Function(trial) -> classified_trial
        num_workers: Number of worker processes (None = auto-detect)
    
    Returns:
        List of classified trials in original order
    """
    if not trials:
        return []
    
    # Determine worker count
    if num_workers is None:
        num_workers = get_optimal_worker_count(len(trials))
    
    logger.info(f"Processing {len(trials)} trials with {num_workers} workers")
    print(f"\nProcessing {len(trials)} trials with {num_workers} parallel workers")
    
    # Create MANY small batches (not just num_workers batches)
    # This ensures the progress bar updates frequently
    batch_size = 10  # Process 10 trials per batch
    num_batches = (len(trials) + batch_size - 1) // batch_size  # Ceiling division
    
    trial_batches = []
    for i in range(0, len(trials), batch_size):
        trial_batches.append(trials[i:i+batch_size])
    
    # Prepare arguments for each batch
    worker_args = [
        (batch, classifier_function, i+1, num_batches)
        for i, batch in enumerate(trial_batches)
    ]
    
    # Process in parallel with progress bar
    classified_trials = []
    with Pool(num_workers) as pool:
        # Create progress bar
        with tqdm(total=len(trials), desc="Classifying trials", unit="trial") as pbar:
            # Process batches - workers will pull from the queue as they finish
            for batch_results in pool.imap_unordered(classify_trial_batch, worker_args, chunksize=1):
                classified_trials.extend(batch_results)
                pbar.update(len(batch_results))
    
    logger.info(f"Completed parallel processing of {len(classified_trials)} trials")
    
    return classified_trials