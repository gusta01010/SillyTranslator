SillyTranslator translates SillyTavern presets and character cards metadata automatically

![alt text](https://files.catbox.moe/gv9j3i.png "Card Message")

<p align="center">
  <img src="https://files.catbox.moe/2hhlx7.png" alt="Card Description">
</p>

## What is SillyTranslator

SillyTranslator is a collection of two tools available to download, containing two utilities:

1. Preset translator tool
2. Card monitoring tool

## Key Features

*   **Basic Interface:** You have an easy way of setting up the tools mentioned above, having a simple terminal interface.
*   **Automatic:** The tool translates presets and .png character cards automatically without having to replace manually descriptions, system messages, prefills and many more.

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

## Usage

### Preset translator
To use the preset translator, first you need to follow these steps:

1. Set up the SillyTavern folder (optional) or use custom folder **(IMPORTANT!)**.

2. Set up the language the preset will be translated to and there is an optional box to select if want to translate content inside <>.
* **Translate wrapped `<>`**: this one is experimental, you can translate any content inside <>, for example, `<think>` can be translated to `<考える>`

3. Select the .JSON files to be translated.

4. Name the file and save it.

### Card translator
To use the card translator, first you need to follow these steps:

1. Set up your interface language.
1. Select the SillyTavern folder **(IMPORTANT!)**.
3. Set up the translator.
Setting up the translator is important, as there are two options:
* **Translate name**: you can translate, the character card name from, for example, `James` (en) to `ジェームズ` (ja) if the option is enabled.
* **Translate wrapped `<>`**: this one is experimental, you can translate any content inside <>, for example, `<think>` can be translated to `<考える>`
* **Translate wrapped `()`**: translates content inside parentheses separated from the rest of the text
* **Translate wrapped `[]`**: translates content inside brackets separated from the rest of the text
* Use Jane (placeholder) instead of {{char}} during translation: Enabling placeholder may improve translation coherence and returns back to {{char}} after the translation is done
  
4. Select the translation service.
5. Enable monitoring.

After enabling the monitoring, it will scan any file inside SillyTavern's character folder to translate, backing up the original file in `Original` folder where the tool is localted, if you want to restore the original files you can press the number `3` in your keyboard and it will restore the files. **The restored original files will not be translated until the second option, `2` is selected, to clean all the translated files status.**

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

## License

This project is licensed under the [MIT License](./LICENSE) - see the `LICENSE` file for details.
