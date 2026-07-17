"""HTTP view modules grouped by API domain.

Views are intentionally not re-exported here. Importing one endpoint should not
eagerly import every workflow module or create background executors as a side
effect; URL configuration imports the required modules explicitly.
"""
