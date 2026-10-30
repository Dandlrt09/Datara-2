"""The terms of use version in force (terms-of-use S1/D3).

The number lives here, and for the person reading it, in the two documents
under ``web/src/content/terms``. ``tests/unit/test_terms_documents.py``
cross-checks the three, so a text cannot be edited without a version bump.

``POST /api/auth/register`` refuses a body that does not carry this exact value
(D5): the account then records which text was accepted, not merely that a box
was ticked.
"""

TERMS_VERSION = "1.0"
