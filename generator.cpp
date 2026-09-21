// Independent reverse generator for the 33-hole English board.
// No external puzzle collection or precomputed solution is used.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

using Board = uint64_t;
struct Move {
    int from, over, to;
    Board mask, reverseSource;
};
struct Node {
    Board board;
    uint32_t parent;
    uint8_t move;
};
struct Options {
    size_t width = 200000;
    double seconds = 120;
    Board seed = 20260921;
    uint64_t maxExpansions = 100000000;
};
std::vector<std::pair<int, int>> cells;
std::vector<Move> moves;
int ids[7][7], symmetry[8][33];
Board transformLookup[8][3][2048] = {};

// Transform three 11-bit chunks; take the minimum across the D4 group.
Board canonical(Board board) {
    Board best = ~Board(0);
    for (int s = 0; s < 8; ++s) {
        Board transformed = transformLookup[s][0][board & 2047]
            | transformLookup[s][1][(board >> 11) & 2047]
            | transformLookup[s][2][(board >> 22) & 2047];
        best = std::min(best, transformed);
    }
    return best;
}

Board hash64(Board x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

void setup() {
    for (auto& row : ids) std::fill(std::begin(row), std::end(row), -1);
    for (int r = 0; r < 7; ++r) {
        for (int c = 0; c < 7; ++c) {
            if ((r >= 2 && r <= 4) || (c >= 2 && c <= 4)) {
                ids[r][c] = cells.size();
                cells.push_back({r, c});
            }
        }
    }
    const std::pair<int, int> directions[] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
    for (int i = 0; i < 33; ++i) {
        auto [r, c] = cells[i];
        for (auto [dr, dc] : directions) {
            int rr = r + 2 * dr, cc = c + 2 * dc;
            if (rr < 0 || rr >= 7 || cc < 0 || cc >= 7 || ids[rr][cc] < 0) continue;
            int j = ids[r + dr][c + dc], k = ids[rr][cc];
            Board mask = (Board(1) << i) | (Board(1) << j) | (Board(1) << k);
            moves.push_back({i, j, k, mask, Board(1) << k});
        }
        for (int s = 0; s < 8; ++s) {
            int rr = r, cc = s >= 4 ? 6 - c : c;
            for (int t = 0; t < s % 4; ++t) {
                int oldRow = rr;
                rr = cc;
                cc = 6 - oldRow;
            }
            symmetry[s][i] = ids[rr][cc];
        }
    }
    for (int s = 0; s < 8; ++s) {
        for (int chunk = 0; chunk < 3; ++chunk) {
            for (int bits = 1; bits < 2048; ++bits) {
                int bit = __builtin_ctz(static_cast<unsigned>(bits));
                transformLookup[s][chunk][bits] = transformLookup[s][chunk][bits & (bits - 1)]
                    | (Board(1) << symmetry[s][11 * chunk + bit]);
            }
        }
    }
}

#ifndef PEG_BOARD_ONLY
Options parseOptions(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        std::string name = argv[i];
        if (name == "--help") {
            std::cout << "Usage: generator [--width 200000] [--seconds 120] "
                         "[--seed 20260921] [--max-expansions 100000000]\n";
            std::exit(0);
        }
        if (i + 1 >= argc) throw std::runtime_error("Missing option value");
        std::string value = argv[++i];
        size_t end = 0;
        if (name == "--seconds") {
            options.seconds = std::stod(value, &end);
        } else {
            if (value.empty() || value[0] == '-') throw std::runtime_error("Invalid positive integer");
            auto number = std::stoull(value, &end);
            if (name == "--width") options.width = number;
            else if (name == "--seed") options.seed = number;
            else if (name == "--max-expansions") options.maxExpansions = number;
            else throw std::runtime_error("Unknown option: " + name);
        }
        if (end != value.size()) throw std::runtime_error("Invalid option value");
    }
    if (!options.width || options.width > 10000000 || !(options.seconds > 0)
        || options.seconds > 3600 || !options.maxExpansions) {
        throw std::runtime_error("Require width 1..10000000, seconds (0,3600], expansions > 0");
    }
    return options;
}

void coordinate(std::ostream& out, int i) {
    out << '[' << cells[i].first << ',' << cells[i].second << ']';
}

int main(int argc, char** argv) {
    try {
        Options options = parseOptions(argc, argv);
        setup();
        auto start = std::chrono::steady_clock::now();
        auto elapsed = [&]() {
            return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        };
        std::vector<Node> layers[33];
        layers[1].push_back({Board(1) << ids[3][3], 0, 0});
        bool exhaustive[33] = {}, visited[33] = {}, pruned[33] = {};
        size_t discovered[33] = {};
        bool ancestorsComplete = true;
        uint64_t expansions = 0;
        std::string stopReason = "all layers processed";

        for (int pegs = 2; pegs <= 32; ++pegs) {
            std::vector<Node> next;
            std::unordered_set<Board> seen;
            seen.reserve(std::min(options.width * 4, layers[pegs - 1].size() * 8));
            bool complete = true;
            for (uint32_t parent = 0; parent < layers[pegs - 1].size(); ++parent) {
                if (expansions >= options.maxExpansions
                    || (parent % 1024 == 0 && elapsed() >= options.seconds)) {
                    complete = false;
                    stopReason = expansions >= options.maxExpansions ? "expansion limit" : "time limit";
                    break;
                }
                Board board = layers[pegs - 1][parent].board;
                ++expansions;
                for (size_t m = 0; m < moves.size(); ++m) {
                    const Move& move = moves[m];
                    if ((board & move.mask) != move.reverseSource) continue;
                    Board child = board ^ move.mask;
                    if (seen.insert(canonical(child)).second) {
                        // Keep the original orientation so parent links need no coordinate conversion.
                        next.push_back({child, parent, static_cast<uint8_t>(m)});
                    }
                }
            }
            visited[pegs] = true;
            discovered[pegs] = next.size();
            exhaustive[pegs] = ancestorsComplete && complete;
            pruned[pegs] = next.size() > options.width;
            if (pruned[pegs]) {
                // Seeded hash ranking samples distinct symmetry classes, not random paths.
                Board salt = hash64(options.seed + pegs);
                auto less = [&](const Node& a, const Node& b) {
                    return hash64(canonical(a.board) ^ salt) < hash64(canonical(b.board) ^ salt);
                };
                std::nth_element(next.begin(), next.begin() + options.width, next.end(), less);
                next.resize(options.width);
            }
            layers[pegs] = std::move(next);
            ancestorsComplete = exhaustive[pegs] && !pruned[pegs];
            std::cout << "pegs=" << pegs << " discovered=" << discovered[pegs]
                      << " retained=" << layers[pegs].size() << " elapsed=" << elapsed() << "s" << std::endl;
            if (!complete) break;
            if (layers[pegs].empty()) {
                stopReason = "frontier exhausted";
                for (int k = pegs + 1; k <= 32; ++k) {
                    visited[k] = true;
                    exhaustive[k] = ancestorsComplete;
                }
                break;
            }
        }

        std::ofstream puzzles("generated-puzzles.json"), solutions("generated-solutions.json");
        std::ofstream report("generation-report.txt");
        if (!puzzles || !solutions || !report) throw std::runtime_error("Cannot open output files");
        puzzles << "{\n";
        solutions << "{\n";
        report << "English board: reverse generation from center; D4 symmetry deduplication\n"
               << "Seed: " << options.seed << "; beam width: " << options.width
               << "; time limit: " << options.seconds << "s; expansion limit: " << options.maxExpansions
               << "\nSearch elapsed: " << elapsed() << "s; expanded states: " << expansions
               << "\nStop reason: " << stopReason
               << "\n100+ means at least 100 saved. Sampled counts are lower bounds.\n"
               << "Unvisited or sampled zero does not prove impossibility.\n"
               << "Solutions align with puzzle array indices and contain forward moves.\n\n"
               << "Pegs | Problems | Discovered classes | Status\n";
        std::cout << "\nPegs | Problems\n";
        for (int pegs = 5; pegs <= 32; ++pegs) {
            size_t count = std::min(size_t(100), layers[pegs].size());
            std::string label = count == 100 ? "100+" : std::to_string(count);
            const char* status = !visited[pegs] ? "not reached"
                : exhaustive[pegs] ? "exhaustive" : "sampled / lower bound";
            std::cout << pegs << " | " << label << '\n';
            report << pegs << " | " << label << " | " << discovered[pegs] << " | " << status << '\n';
            puzzles << "  \"" << pegs << "\": [";
            solutions << "  \"" << pegs << "\": [";
            for (size_t j = 0; j < count; ++j) {
                if (j) { puzzles << ','; solutions << ','; }
                puzzles << "\n    [";
                bool first = true;
                for (int i = 0; i < 33; ++i) {
                    if (!(layers[pegs][j].board & (Board(1) << i))) continue;
                    if (!first) puzzles << ',';
                    coordinate(puzzles, i);
                    first = false;
                }
                puzzles << ']';
                solutions << "\n    [";
                uint32_t index = j;
                for (int level = pegs; level > 1; --level) {
                    const Node& node = layers[level][index];
                    const Move& move = moves[node.move];
                    if (level != pegs) solutions << ',';
                    solutions << "{\"from\":";
                    coordinate(solutions, move.from);
                    solutions << ",\"over\":";
                    coordinate(solutions, move.over);
                    solutions << ",\"to\":";
                    coordinate(solutions, move.to);
                    solutions << '}';
                    index = node.parent;
                }
                solutions << ']';
            }
            puzzles << "\n  ]" << (pegs == 32 ? "\n" : ",\n");
            solutions << "\n  ]" << (pegs == 32 ? "\n" : ",\n");
        }
        puzzles << "}\n";
        solutions << "}\n";
        puzzles.close(); solutions.close(); report.close();
        if (!puzzles || !solutions || !report) throw std::runtime_error("Failed writing output files");
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
#endif
