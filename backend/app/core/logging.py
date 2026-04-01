import logging, sys
def setup_logging(level="INFO"):
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", stream=sys.stdout)
