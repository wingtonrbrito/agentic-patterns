"""Bookstore vertical configuration.

Re-exports the BookstoreConfig from the patterns module,
demonstrating how verticals use the domain config pattern.
"""

from patterns.domain_config import BookstoreConfig

# Default configuration instance
config = BookstoreConfig.default()
