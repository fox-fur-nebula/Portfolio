# Telegram Bot for managing your personal library

## Administrator features
* **Mailing monitoring:** permanent tracking of books and informational messages sent to users.
* **User management:** control the correctness of profile and list storage.
* **Service settings:** configure message format, manage caching of requests to the book database.

## User features
* **Two reading lists:** personal lists “Planned” and “Read.”
* **List management:** adding and deleting books, editing entries in both lists.
* **Searching for book information:** by title or title and author, the bot returns the number of pages and a description of the work.

## Technical features
* **Integration with Google Books API:** retrieval of metadata (pages, description) upon user request.
* **Data storage:** all users and their lists are saved in a JSON file; restart resistance is ensured.
* **Query cache:** all requested books are saved locally to speed up subsequent responses and reduce the load on the external API.
* **Accurate search:** and filtering: the search and data processing mechanism in JSON ensures the reliability of author and title information, eliminating duplication and errors.