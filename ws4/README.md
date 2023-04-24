# CMPE487 - Workshop 4

### Environment Information: 
- Who I have tested with: **Artun Akdogan**
- OS: MacOS Ventura (13.1 (22C65))
### PCAP file is too big for Moodle, so here is the Drive link for it: https://drive.google.com/file/d/1yxQU6IM_0yHPMYuu3Wak-O6rEKYpjlBW/view

### Usage
Usage of the script:
- Run `python netchat.py`. It requires that `nmap` to be installed on your system. 
    - Note: `nmap` takes a long time :D 
- You can use commands:
    - `:send`: `:send <WHO> <MESSAGE>` -> `:send deniz hello there` : Sends message to the person you select.
    - `:peers`: `:peers`: Lists all your peers.
    - `:hello`: `:hello <IP_ADDR>`: Sends `hello` message to the `IP_ADDR`.
    - `:quit`: Exits the program.
    - `:whoami`: Shows your `<IP_ADDR>` and `<NAME>`.
    - `:send_file`: You can send files using this command. `:send_file` `<RECIPIENT>` `<FILEPATH>` 

## There is a Dockerfile if you want to use containers.
```
docker build . -t ws4_cmpe487
docker run --rm -it --entrypoint bash ws4_cmpe487
```

## Notes
-- `requirements.txt` file has some dependencies, but they are for the linter and formatter. If you don't have them, it's OK.
-- It's under MIT license, so you can distribute if you want.