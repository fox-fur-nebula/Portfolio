# Telegram Bot for weather forecasts

## Administrator features
* **Performance monitoring:** tracking the accuracy of parsing and the relevance of forecasts.
* **User management:** control saved profiles and city history, restore data if necessary.
* **Bot settings:** adjust cache update frequency, filtering parameters, and amount of stored information.

## User features
* **City selection:** specify your city to get an up-to-date forecast.
* **Flexible viewing:** the ability to find out the weather for today, the week, or 10 days.
* **Change city:** you can change the selected city at any time using the bot command.
* **Data storage:** when reusing after unsubscribing, the bot will offer the last saved city.

## Technical features

* **Sinoptik parsing:** get accurate weather forecasts from the Sinoptik website.
* **Data storage:** user cities are saved in a JSON file for easy profile recovery.
* **Local cache:** forecasts for specific cities are filtered and saved in JSON, which speeds up response time and reduces the load on the source.
* **Adaptability:** support for multi-user mode with individual parameter storage for each profile.