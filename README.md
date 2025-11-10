SillyTranslator translates SillyTavern presets and character cards metadata automatically

![alt text](https://files.catbox.moe/gv9j3i.png "Card Message")

<p align="center">
  <img src="https://files.catbox.moe/2hhlx7.png" alt="Card Description" width=600>
</p>

## What is SillyTranslator

SillyTranslator is a collection of two tools available to download, containing two utilities:

1. **Preset translator script**
    - Translates .json presets automatically and saves them in the specified location.

2. **Card translator script**
    - Monitors the SillyTavern's  `characters` folder for character cards, translates and saves them in the `characters` folder.

## Key Features

*   **Basic Interface:** You have an easy way of setting up the tools mentioned above, having a simple terminal interface.
*   **Automatic:** The tool translates presets and .png character cards automatically and saves them for you.

* **Supported languages:** 
  * 🇷🇺 Russian
  * 🇧🇷 Portuguese
  * 🇯🇵 Japanese
  * 🇨🇳 Chinese
  * 🇰🇷 Korean
  * 🇮🇹 Italian
  * 🇫🇷 French
  * 🇬🇧 English
  * 🇩🇪 German
  * 🇪🇸 Spanish

## Requirements
* ~~ImageMagick:~~

~~Requires ImageMagick to be installed and configure the PATH variable.--~~
ImageMagick installation is not necessary anymore, just have the `requirements.txt` packages listed there

## Usage

## Preset translator
To use the preset translator, first you need to follow these steps:

**0.** Run `main.py`.

**1.** Set up the SillyTavern folder or use a custom folder location to save the files.

**2.** If you want to use LLM to translate: mark the checkbox `Translate using LLM`.
* Select your provider (Currently only supports openrouter/groq) and insert the API Key and model name from the provider. **(IMPORTANT!)**.


**3.** Select the language that will translate the preset.

* There is an optional box to select if want to translate content inside <>:
* **Translate content inside <`...`> bracket**: this one is experimental, you can translate any content inside <>, for example, `<think>` can be translated to `<考える>`

**4.** Select the .JSON files to be translated.


**5.** Click **Start Translation**.

After the translation is finished, you can find the file in the folder you have saved.

## Card translator
To use the card translator, first you need to follow these steps:

**0.** Run `card_translator.py`.

**1.** Select the SillyTavern folder in `3. Configure Settings` by configuring the `1. Characters Directory` **(IMPORTANT!)**.

**2.** Set up the translator.\
Setting up the translator is important, customizations for Non-LLMs and LLMs at `Configure Settings`:

**3.** Set up the `Translation Service`
*  It can be Non-LLM (Google Translate) or LLM (Groq/Openrouter)

**4.** Set up the `API Provider`, `Model` and `API Key`

**5.** Extras settings

* **`Translate Names`**: you can translate, the character card name from, for example, `James` (en) to `ジェームズ` (ja) if the option is enabled.
* **`Translate Alternate Greetings`**: you can disable or enable the translation of alternate greetings.
  *  This option can be resource-heavy depending on how many alternate greetings the character have!
* **`Use Character Name`**: you can use the Character's name instead of {{char}} when found as reference when translating.
  

  
**6.** Return with `10. Back to main menu` and Enable monitoring.

After enabling the monitoring, it will scan any file inside SillyTavern's character folder to translate, backing up the original file in `Original` folder where the tool is located, if you want to restore the original files you can press the number `4. Restore Originals` and it will restore the files. **The restored original files will not be translated until the fifth option, `5. Clear Database` is selected, to clean all the translated files status.**

## Contributing

Contributions are very welcome! If you'd like to contribute, please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Make your changes and commit them.
4. Submit a pull request to the branch.

## Questions or Suggestions?

Feel free to open an issue on GitHub or send me a direct message on Discord:

*   Discord: sonic\_8783

## Image: Prompt comparison - English to Portuguese

![alt text](https://files.catbox.moe/ga0w87.png "Preset")
###### * The translation may not be 100% accurate.
## License

This project is licensed under the [MIT License](./LICENSE) - see the `LICENSE` file for details.
