import logging
from pipeline import main as pipeline_main


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


if __name__ == "__main__":
    pipeline_main()

