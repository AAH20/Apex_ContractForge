// SPDX-License-Identifier: Apache-2.0
// Generated Tick-profile CPU transition executor. Not a physical trading adapter.
#include <array>
#include <charconv>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>

struct Event {
    bool reset, recover, terminal_valid, valid, frame_ok, out_ready;
    uint64_t terminal_id, seq, limit;
    uint16_t instrument;
    uint32_t price, qty, epoch, rate_limit;
};
struct Pending { bool occupied=false, sent=false; uint64_t id=0; uint32_t qty=0; };
struct State {
    bool hold=true, out_valid=false;
    uint64_t exposure=0, expected=1, next_id=1, max_exposure=16, out_id=0;
    uint32_t epoch=0, threshold=100, order_qty=1, rate_limit=16, out_price=0, out_qty=0;
    uint16_t out_instrument=0;
    uint8_t rate=0;
    uint8_t window=0;
    unsigned status=0;
    std::array<uint32_t,8> ask{};
    std::array<Pending,16> pending{};
};

static bool step(State& s, const Event& e) {
    const bool ready = !s.hold && !e.terminal_valid && !e.recover && (!s.out_valid || e.out_ready);
    if(e.reset) { s=State{}; return ready; }
    s.status=0;
    
    if(s.out_valid && e.out_ready) {
        for(auto& p:s.pending) if(p.occupied && p.id==s.out_id) p.sent=true;
        s.out_valid=false;
    }
    if(true) {
        if(s.window==63) { s.window=0; s.rate=0; }
        else ++s.window;
    }
    const uint32_t effective_rate=s.rate;
    if(e.recover) {
        if(s.hold && s.exposure==0 && !s.out_valid && e.epoch>s.epoch && e.qty>0 && e.limit>0 && e.rate_limit>0 && e.seq>0) {
            s.hold=false; s.epoch=e.epoch; s.expected=e.seq; s.threshold=e.price; s.order_qty=e.qty;
            s.max_exposure=e.limit; s.rate_limit=e.rate_limit; s.rate=0; s.window=0;
        }
    } else if(e.terminal_valid) {
        int slot=-1;
        for(int k=0;k<16;++k) if(s.pending[k].occupied && s.pending[k].id==e.terminal_id) slot=k;
        if(slot>=0 && s.pending[slot].sent) {
            s.exposure-=s.pending[slot].qty; s.pending[slot].occupied=false; s.pending[slot].sent=false; s.status=8;
        } else s.status=9;
    } else if(e.valid && ready) {
        if((!e.frame_ok) || (e.epoch != s.epoch) || (e.instrument >= UINT64_C(8)) || (e.price == UINT64_C(0)) || (e.qty == UINT64_C(0))) { s.hold=true; s.status=1; }
        else if(e.seq < s.expected) s.status=2;
        else if((e.seq != s.expected) || (s.expected == UINT64_C(18446744073709551615))) { s.hold=true; s.status=3; }
        else {
            ++s.expected; s.ask[e.instrument]=e.price;
            int free_slot=-1;
            for(int k=0;k<16;++k) if(!s.pending[k].occupied && free_slot==-1) free_slot=k;
            if((e.price > s.threshold) || (e.qty < s.order_qty)) s.status=6;
            else if(free_slot<0 || ((static_cast<unsigned __int128>(s.exposure) + static_cast<unsigned __int128>(s.order_qty)) > static_cast<unsigned __int128>(s.max_exposure)) || effective_rate >= s.rate_limit) s.status=4;
            else if(s.next_id == UINT64_C(18446744073709551615)) { s.hold=true; s.status=7; }
            else {
                s.pending[free_slot]={true,false,s.next_id,s.order_qty};
                s.out_valid=true; s.out_id=s.next_id; s.out_instrument=e.instrument; s.out_price=e.price; s.out_qty=s.order_qty;
                ++s.next_id; s.exposure=s.exposure + s.order_qty; s.rate=effective_rate+1; s.status=5;
            }
        }
    }
    return ready;
}

static Event parse(const std::string& line) {
    std::istringstream input(line); std::array<uint64_t,14> v{}; std::string token;
    for(auto& x:v) {
        if(!(input>>token)) throw std::runtime_error("trace row has fewer than 14 fields");
        auto [end,ec]=std::from_chars(token.data(),token.data()+token.size(),x);
        if(ec!=std::errc{} || end!=token.data()+token.size()) throw std::runtime_error("invalid unsigned trace field");
    }
    if(input>>token) throw std::runtime_error("trace row has extra fields");
    for(int i:{0,1,2,4,5,13}) if(v[i]>1) throw std::runtime_error("invalid Boolean trace field");
    if(v[7]>UINT16_MAX) throw std::runtime_error("instrument exceeds u16");
    for(int i:{8,9,10,12}) if(v[i]>UINT32_MAX) throw std::runtime_error("field exceeds u32");
    return {bool(v[0]),bool(v[1]),bool(v[2]),bool(v[4]),bool(v[5]),bool(v[13]),v[3],v[6],v[11],
            static_cast<uint16_t>(v[7]),static_cast<uint32_t>(v[8]),static_cast<uint32_t>(v[9]),static_cast<uint32_t>(v[10]),static_cast<uint32_t>(v[12])};
}

static void observe(std::ostream& out, const State& s, bool ready) {
    out << ready << ' ' << s.out_valid << ' ' << (s.out_valid?s.out_id:0) << ' ' << (s.out_valid?s.out_instrument:0)
        << ' ' << (s.out_valid?s.out_price:0) << ' ' << (s.out_valid?s.out_qty:0) << ' ' << s.hold << ' ' << s.exposure
        << ' ' << s.expected << ' ' << s.status << ' ' << s.epoch << ' ' << s.threshold << ' ' << s.order_qty
        << ' ' << s.max_exposure << ' ' << s.rate_limit << ' ' << +s.rate << ' ' << +s.window << ' ' << s.next_id;
    for(auto price:s.ask) out << ' ' << price;
    for(const auto& p:s.pending) out << ' ' << p.occupied << ' ' << p.sent << ' ' << p.id << ' ' << p.qty;
    out << '\n';
}

int main(int argc, char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("usage: core INPUT_TRACE OUTPUT_TRACE");
        std::ifstream input(argv[1]); std::ofstream output(argv[2]);
        if(!input || !output) throw std::runtime_error("cannot open trace files");
        State state; std::string line;
        while(std::getline(input,line)) { auto e=parse(line); auto ready=step(state,e); observe(output,state,ready); }
        output.flush(); if(!output || input.bad()) throw std::runtime_error("trace I/O failure");
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 2; }
}
