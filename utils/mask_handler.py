from pathlib import Path
import numpy as np
from skimage import io
import matplotlib.pyplot as plt
from typing import Tuple, List
import logging

logger = logging.getLogger(__name__)

def load_mask(base_path: str, name: str, invert: bool = False) -> np.ndarray:
    """
    Load and process a mask from file
    
    Args:
        base_path: Directory path where masks are stored
        name: Filename of the mask
        invert: Whether to invert the mask values
        
    Returns:
        Processed mask as numpy array
        
    Raises:
        FileNotFoundError: If mask file doesn't exist
        ValueError: If mask file is invalid
    """
    try:
        mask_path = Path(base_path) / name
        if not mask_path.exists():
            raise FileNotFoundError(f"Mask file not found: {mask_path}")
        
        # Load mask and extract first channel if it's RGB
        mask = io.imread(str(mask_path))
        if mask.ndim == 3:
            mask = mask[:, :, 0]
            
        # Process mask
        if invert:
            mask = ~mask
            mask = (mask >= 128).astype(np.uint8)
        
        # Validate mask
        unique_values = np.unique(mask)
        logger.info(f"Mask unique values: {unique_values}")
        if not np.all(np.isin(unique_values, [0, 1, 255])):
            logger.warning("Mask contains unexpected values")
        
        # Optional visualization
        plt.figure(figsize=(8, 8))
        plt.imshow(mask, cmap='gray')
        plt.title(f"Loaded mask: {name}")
        plt.colorbar()
        plt.show()
        
        return mask
        
    except Exception as e:
        logger.error(f"Error loading mask {name}: {str(e)}")
        raise



def tile_array(array: np.ndarray, 
               tile_width: int = 800,
               tile_height: int = 600
               ) -> Tuple[List[List[np.ndarray]], int, int]:
    """
    Split array into tiles of specified size and arrange them in a 2D list (row-major).

    Args:
        array: Input array to tile
        tile_width: Width of each tile
        tile_height: Height of each tile
        
    Returns:
        A tuple containing:
        - 2D list (grid) of tiles with shape [grid_height][grid_width]
        - grid_width
        - grid_height
        
    Raises:
        ValueError: If array dimensions don't match tile size
    """
    height, width = array.shape[:2]
    
    # Validate dimensions
    if (height % tile_height != 0) or (width % tile_width != 0):
        raise ValueError(
            f"Array dimensions ({height}x{width}) must be divisible by "
            f"tile dimensions ({tile_height}x{tile_width})."
        )
    
    grid_height = height // tile_height
    grid_width = width // tile_width
    
    # Create a 2D list of placeholders
    tiles = [[None for _ in range(grid_width)] for _ in range(grid_height)]
    
    # Fill tiles row by row, col by col
    for row in range(grid_height):
        for col in range(grid_width):
            tile = array[
                row * tile_height : (row + 1) * tile_height,
                col * tile_width  : (col + 1) * tile_width
            ]
            tiles[row][col] = tile
    
    return tiles, grid_width, grid_height


def visualize_tiles(tiles: List[List[np.ndarray]]):
    """
    Visualize tiles arranged in a 2D list (row-major).

    Args:
        tiles: A 2D list of tiles, i.e. tiles[row][col].
               Each tile is a NumPy array.
    """
    # Determine grid size from the shape of the tiles list
    grid_height = len(tiles)
    grid_width = len(tiles[0]) if grid_height > 0 else 0

    fig, axs = plt.subplots(grid_height, grid_width, figsize=(15, 15))
    # Special case: if there's only one tile total
    if grid_height == 1 and grid_width == 1:
        axs.imshow(tiles[0][0], cmap='gray')
        axs.set_title('Tile 0,0')
        axs.axis('off')
        plt.tight_layout()
        plt.show()
        return

    for row in range(grid_height):
        for col in range(grid_width):
            tile = tiles[row][col]
            # axs will be 2D only if both dimensions > 1
            if grid_height == 1:  
                # Only one row
                ax = axs[col]
            elif grid_width == 1:
                # Only one column
                ax = axs[row]
            else:
                ax = axs[row, col]


            ax.imshow(tile, cmap='gray')
            ax.set_title(f'Tile {row},{col}')
            ax.axis('off')

    plt.tight_layout()
    plt.show()
