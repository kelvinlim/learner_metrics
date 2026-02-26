I want to create a multi-tenant app to assist NIH and other training programs to easily keep track and report on common metrics requested by
the training programs.

Multi-tenant so it could support multiple institutions. Within each institution could have multiple unit levels - model this on the project in the runway app. 

For authentication start with google auth.

We would use the hiearchical rbac used in runway app.

The initial areas for tracking would be be grants and publications.

For grants, we would use nih reporter.  We would first determine if they have an investigator id. This would ease their project retrieval in the future.  We would store every project in our database.  See the code in the dept_dashboard app for geting the users nih investigator info

For publications, we would use the pubmed.gov and orcid.org.  See the runway app for how to retrieve the orcid id but modify it to also change the name.  For pubmed searches 
we could include the actual pubmed query to support greater specificity for example the institution including the name.
Being able to test that interactively in the interface would be an optional feature.

Use postgres for database
Use react/fastapi
use alembic for migrations
Use podman for containers
Set up for dev/staging and blue/green deployment

