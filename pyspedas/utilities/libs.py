"""
Displays location of source files, one line of documentation and the function name based on the request
"""

import importlib
import inspect
import itertools
import pkgutil
import sys
import io

import pytplot
import pyspedas


def libs(function_name, package=None):
    """
    Searches for a specified function within a given package and its submodules,
    and prints information about the function if found. The search is performed
    utilizing the imports defined in each __init__.py package file to display the
    callable function name.

    Parameters:
    - function_name (str): The name or partial name of the function to search for.
    - package (module, optional): The Python package in which to search for the function.
      Default is the pyspedas package. This should be a Python module object.

    Note:
    - All submodules of pyspedas and pytplot are imported during the search. The package option is
      simply narrows the search.
    - The function specifically searches for functions, not classes or other objects.
    - If multiple functions with the same name exist in different modules within the package,
      it will list them all.
    - The function handles ImportError exceptions by printing an error message and
      continuing the search, except 'pytplot.QtPlotter'. pytplot.QtPlotter results in error during import and ignored

    Example Usage:
    ```python
    pyspedas.utilities.libs('fgm')

    pyspedas.utilities.libs('fgm', package=pyspedas.mms)
    ```
    """

    # Gate for no function_name
    if not function_name:
        return

    def list_functions(module, root, function_name, pacakge_obj):
        full_module_name = module.__name__
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and (function_name in name) and (pacakge_obj.__name__ in obj.__module__):
                full_name = full_module_name + '.' + name
                source_file = inspect.getsourcefile(obj)
                doc = inspect.getdoc(obj)
                first_line_of_doc = doc.split('\n')[0] if doc else "No documentation"
                print(f"Function: {full_name}\nLocation: {source_file}\nDocumentation: {first_line_of_doc}\n")

    def traverse_modules(package, function_name, pacakge_obj):
        # Add the module itself
        walk_packages_iterator = pkgutil.walk_packages(path=package.__path__, prefix=package.__name__ + '.')
        combined_iterator = itertools.chain(((None, package.__name__, True),), walk_packages_iterator)

        for _, modname, ispkg in combined_iterator:
            if ispkg and 'qtplotter' not in modname.lower():
                # Save the current stdout so that we can restore it later
                original_stdout = sys.stdout

                # Redirect stdout to a dummy stream
                sys.stdout = io.StringIO()

                try:
                    module = importlib.import_module(modname)
                    if not pacakge_obj:
                        pacakge_obj = package

                    # Restore the original stdout
                    sys.stdout = original_stdout
                    list_functions(module, package, function_name, pacakge_obj)
                except ImportError as e:
                    # Restore the original stdout
                    sys.stdout = original_stdout
                    print(f"Error importing module {modname}: {e}")
                finally:
                    # Restore the original stdout
                    sys.stdout = original_stdout

    for module in [pyspedas, pytplot]:
        if not package or module.__name__ in package.__name__:
            traverse_modules(module, function_name, package)
