Sidewalkreator
=================

Generate candidate sidewalk, crossing and kerb geometries from street data
with Python, without QGIS. Install the ``sidewalkreator`` distribution from
PyPI and import ``headless_sidewalkreator``.

The :doc:`parameter reference <parameters>` is the main guide to configuring
the pipeline. It explains defaults, units, interactions, validation and which
controls each public API supports. Defaults and the road-width table
are read from the implementation at each documentation build.

.. code-block:: bash

   python -m pip install sidewalkreator

Start with :doc:`quickstart` for a short example, or consult
the complete :doc:`parameter reference <parameters>`.

.. toctree::
   :maxdepth: 2
   :caption: Using Sidewalkreator

   quickstart
   parameters
   api

.. toctree::
   :maxdepth: 1
   :caption: Maintaining and publishing

   maintaining
   publishing

.. note::

   This reference follows the development branch. The parameter fixes described
   here are not part of the published PyPI 0.1.0 wheel yet. Use a checkout of this
   branch (``python -m pip install .``) to use them until the next release.
   Check the installed version when reproducing a run.
