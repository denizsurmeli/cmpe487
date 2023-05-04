# CMPE487 Final Project
# Participants
- Artun Akdoğan (artun.akdogan@boun.edu.tr)
- Deniz Sürmeli (deniz.surmeli@boun.edu.tr)
# Game Structure
- First, an initiator broadcasts that she will start a game with `k` koylu's and `v` vampires. 
- Other participants join the game whether they want or not
- When initiator is satisfied with the participation, she starts the game
- *Role Distribution*: Each participant of the game is assigned a role.
- *Game Phase*: The logic of the game.

# Roles and Descriptions
- `Koylu`: A participant that tries to capture all vampires. They can vote for killing.
- `Vampire`: A participant that tries to kill all koylus. They can vote for killing.
- `Doctor`: A koylu with special ability that each round, they can select a koylu for protecting that night, so that that night if a vampire attacks the koylu they are protecting, they don't die and the vampire that attacks them is caught. They can vote for killing.
# Implementation Strategies
- *Role Distribution*: We have two possible strategies.
    - Naive Way: The leader shuffles two lists, one with `ID`s, other with `ROLE`s, zips the items and assigns the roles for each participant in the game. This has the problem where the leader's node knows everyones role. 
    - Better Way: Leader creates role keys and sends them randomly. After that, each player should send those keys again to random nodes. Those keys will be encrypted, so the middle node won't know the key's content and the leader won't know the person who got the key. However, this approach needs $n^2+n$ communication and lengthen the development time significantly.
- *Game Phase* :     
    - 60 seconds of communications. 
    - After that, first discussion period with updated state if vampires have killed someone or not, nominate a participant to blame or not in 30 seconds.
    If the vote for killing is lower than the skipping vote, there is no effect for that round. If there is one leading participant to be killed, they are killed. Else, the voting has no effect and no one is killed.
    - **THE ONE WHO GETS KILLED MUST HONESTLY BROADCAST THEIR ROLE.**
    - If there are only vampires after the voting, the round is won by vampires, else the game continues untill all vampires are caught or vampires won.
    - Else, the vampires select the participants they will kill in 15 seconds.
- After the game phase, the network is available for a new game.

# Project Planning
- Week 1: Solving the Role Distribution Problem, extending the chat application to be a chatroom.
- Week 2: Implementing game logic.
- Week 3: Refactoring, preparing for presentation.

## NOTES:
- We might or not implement the doctor role.