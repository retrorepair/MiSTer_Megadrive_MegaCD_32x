library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
library STD;
use IEEE.NUMERIC_STD.ALL;

entity CDC is
	port(
		CLK			: in std_logic;
		RESET_N		: in std_logic;
		ENABLE		: in std_logic;
		PALSW			: in std_logic;					-- 53.20 MHz (PAL) instead of 53.69 MHz on CLK
		CLKEN_P 		: in std_logic;
		CLKEN_N 		: in std_logic;
		
		DI				: in std_logic_vector(7 downto 0);
		DO				: out std_logic_vector(7 downto 0);
		CS_N			: in std_logic;
		RS				: in std_logic;
		RD_N			: in std_logic;
		WR_N			: in std_logic;
		INT_N			: out std_logic;
		
		HDO			: out std_logic_vector(7 downto 0);
		HRD_N			: in std_logic;
		DTEN_N		: out std_logic;
		WAIT_N		: out std_logic;
		
		CD_DI			: in std_logic_vector(15 downto 0);
		CD_WR			: in std_logic;
		
		RAM_A_WR   	: out std_logic_vector(15 downto 1);
		RAM_A_RD   	: out std_logic_vector(15 downto 0);
		RAM_DI		: in std_logic_vector(7 downto 0);
		RAM_DO		: out std_logic_vector(15 downto 0);
		RAM_WE		: out std_logic;

		-- single-cycle pulses, counted in the top level (tools/phase19_sector_rate.py)
		DBG_SECTOR_END	: out std_logic;
		DBG_DEC_FRAME	: out std_logic;
		DBG_DEC_MID		: out std_logic
	);
end CDC;

architecture rtl of CDC is
	
	--IFSTAT bits
	constant STEN : integer := 0;
	constant DTEN : integer := 1;
	constant STBSY : integer := 2;
	constant DTBSY : integer := 3;
	constant DECI : integer := 5;
	constant DTEI : integer := 6;
	constant CMDI : integer := 7;
	
	--IFCTRL bits
	constant SOUTEN : integer := 0;
	constant DOUTEN : integer := 1;
	constant STWAI : integer := 2;
	constant DTWAI : integer := 3;
	constant CMDBK : integer := 4;
	constant DECIEN : integer := 5;
	constant DTEIEN : integer := 6;
	constant CMDIEN : integer := 7;
	
	--CTRL0 bits
	constant PRQ : integer := 0;
	constant QRQ : integer := 1;
	constant WRRQ : integer := 2;
	constant ERAMRQ : integer := 3;
	constant AUTORQ : integer := 4;
	constant EO1RQ : integer := 5;
	constant EDCRQ : integer := 6;
	constant DECEN : integer := 7;
	
	--CTRL1 bits
	constant SHDREN : integer := 0;
	constant MBCKRQ : integer := 1;
	constant FORMRQ : integer := 2;
	constant MODRQ : integer := 3;
	constant COWREN : integer := 4;
	constant OSCREN : integer := 5;
	constant SYDEN : integer := 6;
	constant SYIEN : integer := 7;
	
	--STAT0 bits
	constant UCEBLK : integer := 0;
	constant ERABLK : integer := 1;
	constant SBLK : integer := 2;
	constant WSHORT : integer := 3;
	constant LBLK : integer := 4;
	constant NOSYNC : integer := 5;
	constant ILSYNC : integer := 6;
	constant CRCOK : integer := 7;
	
	--STAT2 bits
	constant RFORM0 : integer := 0;
	constant RFORM1 : integer := 1;
	constant NOCOR : integer := 2;
	constant MODE : integer := 3;
	constant RMOD0 : integer := 4;
	constant RMOD1 : integer := 5;
	constant RMOD2 : integer := 6;
	constant RMOD3 : integer := 7;
	
	--STAT3 bits
	constant CBLK : integer := 5;
	constant WLONG : integer := 6;
	constant VALST : integer := 7;
	
	signal EN : std_logic;
	
	-- LC8951 address register is 5 BITS (mcd-verificator CDC REGS test 01 writes 0xFFFF to
	-- FF8004 and requires the word read back to be 0x071F, i.e. AR = 0x1F).  Only 0..15 select
	-- a register; AR >= 16 must not alias onto one (CDC REGS test 0C).
	signal AR : std_logic_vector(4 downto 0);
	-- Decode index for the WRITE-side cases: steer AR >= 16 to R14, which none of the write
	-- decodes implement, so those accesses fall through "when others" and change nothing.
	signal ARD : std_logic_vector(3 downto 0);
	signal IFCTRL : std_logic_vector(7 downto 0);
	signal IFSTAT : std_logic_vector(7 downto 0) := x"FF";
	signal DBC : std_logic_vector(15 downto 0);
	signal DAC : std_logic_vector(15 downto 0);
	signal HEAD0 : std_logic_vector(7 downto 0);
	signal HEAD1 : std_logic_vector(7 downto 0);
	signal HEAD2 : std_logic_vector(7 downto 0);
	signal HEAD3 : std_logic_vector(7 downto 0);
	signal PT : std_logic_vector(15 downto 0);
	signal WA : std_logic_vector(15 downto 0);
	signal CTRL0 : std_logic_vector(7 downto 0);
	signal CTRL1 : std_logic_vector(7 downto 0);
	signal STAT0 : std_logic_vector(7 downto 0) := x"00";
	constant STAT1 : std_logic_vector(7 downto 0) := x"00";
	signal STAT2 : std_logic_vector(7 downto 0) := x"00";
	signal STAT3 : std_logic_vector(7 downto 0) := x"80";
	
	signal OLD_WR_N : std_logic;
	signal OLD_RD_N : std_logic;
--	signal OLD_HRD_N : std_logic;
	signal WR_F : std_logic;
	signal RD_F : std_logic;
--	signal HRD_R : std_logic;
--	signal HRD_F : std_logic;
	signal REG_WR : std_logic;
	signal REG_RD : std_logic;
	
	type TransferState_t is (
		TS_IDLE,
		TS_WAIT,
		TS_RAM_READ,
		TS_FIFO,
		TS_SEND_WAIT,
		TS_SEND
	);
	signal TS : TransferState_t;
	signal TRANS_RUN : std_logic;
	signal FIFO_DATA0 : std_logic_vector(8 downto 0);
--	signal FIFO_DATA1 : std_logic_vector(8 downto 0);
--	signal FIFO_RD_POS : std_logic;
--	signal FIFO_WR_POS : std_logic;
	signal DT_EN : std_logic;
	
	signal CD_WR_OLD : std_logic;
	signal WORD_CNT : unsigned(10 downto 0);
	signal RAM_POS : unsigned(11 downto 0);
	signal DEC_POS : unsigned(11 downto 0);
	signal DEC_ADDR : std_logic_vector(15 downto 0);
	signal DEC_DAT : std_logic_vector(15 downto 0);
	signal DEC_WR : std_logic;
	signal DEC_WR_EN : std_logic;
	signal DEC_HEAD01 : std_logic_vector(15 downto 0);
	signal DEC_HEAD23 : std_logic_vector(15 downto 0);
	signal FRAME_CNT : unsigned(19 downto 0);	-- 75 Hz decoder frame timer (53.69 MHz clocks)
	signal DEC_FRAME : std_logic;				-- frame boundary pulse
	signal DEC_MID : std_logic;					-- ~40% into the frame: DECI returns to 1
	signal FRAME_END : unsigned(19 downto 0);	-- clocks per 75 Hz frame - 1, by region
	signal FRAME_MID : unsigned(19 downto 0);	-- 40% of the frame
	signal SECTOR_END : std_logic;				-- a full sector arrived from the drive
	signal SECTOR_ACTIVE : std_logic;			-- between a sector's first and last word

--	signal DECI_WAIT_CNT : unsigned(15 downto 0);
--	signal DECI_SET : std_logic;
	signal OLD_WRRQ : std_logic;
	
begin

	ARD <= AR(3 downto 0) when AR(4) = '0' else x"E";

	EN <= ENABLE and (CLKEN_N or CLKEN_P);
	
	process( RESET_N, CLK )
	begin
		if RESET_N = '0' then
			OLD_WR_N <= '1';
			OLD_RD_N <= '1';
		elsif rising_edge(CLK) then
			if EN = '1' then
				OLD_WR_N <= WR_N;
				OLD_RD_N <= RD_N;
			end if;
		end if;
	end process;
	
	WR_F <= not WR_N and OLD_WR_N;
	RD_F <= not RD_N and OLD_RD_N;
	
	REG_WR <= not CS_N and WR_F and RS;
	REG_RD <= not CS_N and RD_F and RS;
	
	process( RESET_N, CLK )
	begin
		if RESET_N = '0' then
			AR <= (others => '0');
			IFCTRL <= (others => '0');
			CTRL0 <= (others => '0');
			CTRL1 <= (others => '0');
			STAT0(CRCOK) <= '0';
			STAT2(MODE) <= '0';
			STAT2(NOCOR) <= '0';
			DO <= (others => '0');
		elsif rising_edge(CLK) then
			if EN = '1' then
				if CS_N = '0' and WR_F = '1' then
					if RS = '0' then
						AR <= DI(4 downto 0);
					else
						case ARD is
							when x"0" =>			--R0
							when x"1" =>			--R1 IFCTRL
								IFCTRL <= DI;	
							when x"A" =>			--R10 CTRL0
								CTRL0 <= DI;
								STAT0(CRCOK) <= DI(DECEN);
								if DI(AUTORQ) = '1' then
									STAT2(MODE) <= CTRL1(MODRQ);
								else
									STAT2(MODE) <= CTRL1(MODRQ);
									STAT2(NOCOR) <= CTRL1(FORMRQ);
								end if;
							when x"B" =>			--R11 CTRL1
								CTRL1 <= DI;
								if CTRL0(AUTORQ) = '1' then
									STAT2(MODE) <= DI(MODRQ);
								else
									STAT2(MODE) <= DI(MODRQ);
									STAT2(NOCOR) <= DI(FORMRQ);
								end if;
							when x"F" =>			--R15 RESET
								IFCTRL <= (others => '0');
								CTRL0 <= (others => '0');
								CTRL1 <= (others => '0');
							when others => null;
						end case;
						if AR /= "00000" then
							AR <= std_logic_vector( unsigned(AR) + 1 );
						end if;
					end if;
				elsif CS_N = '0' and RD_F = '1' then
					if RS = '0' then
						DO <= "000" & AR;
					else
						case AR(3 downto 0) is
							when x"0" =>			--R0
								
							when x"1" =>			--R1 IFSTAT
								DO <= IFSTAT;	
							when x"2" =>			--R2 DBCL
								DO <= DBC(7 downto 0);
							when x"3" =>			--R3 DBCH
								-- DBC is 12 bits on the LC8951, so DBCH reads back only its top
								-- nibble; bits 7:4 are not stored and read 0.  mcd-verificator CDC
								-- REGS sub-test 0B writes DBCH = 0xFA and requires 0x0A back.  (The
								-- transfer machine parks 0000/1111 in DBC(15:12) as its own flag,
								-- which must not be visible here either.)
								DO <= x"0" & DBC(11 downto 8);
							when x"4" =>			--R4 HEAD0
								DO <= HEAD0;
							when x"5" =>			--R5 HEAD1
								DO <= HEAD1;
							when x"6" =>			--R6 HEAD2
								DO <= HEAD2;
							when x"7" =>			--R6 HEAD3
								DO <= HEAD3;
							when x"8" =>			--R8 PTL
								DO <= PT(7 downto 0);
							when x"9" =>			--R9 PTH
								DO <= PT(15 downto 8);
							when x"A" =>			--R10 WAL
								DO <= WA(7 downto 0);
							when x"B" =>			--R11 WAH
								DO <= WA(15 downto 8);
							when x"C" =>			--R12 STAT0
								DO <= STAT0;
							when x"D" =>			--R13 STAT1
								DO <= STAT1;
							when x"E" =>			--R14 STAT2
								DO <= STAT2;
							when x"F" =>			--R15 STAT3
								DO <= STAT3;
							when others => null;
						end case;
						-- The read decode covers all 16 registers, so unlike the write side it
						-- cannot be steered to an unimplemented index: override afterwards so an
						-- AR >= 16 data-port read does not return a real register's value
						-- (mcd-verificator CDC REGS test 0C reads with AR = 0x12 and requires it
						-- not to alias onto DBCL/DBCH).
						if AR(4) = '1' then
							-- AR >= 16 selects no register, and reads back all-ones (open bus).
							-- Two tests pin this value between them:
							--   CDC REGS 0C  reads twice at AR=0x12 and requires "not 0x0095" then
							--                "not 0x000A", so it can be neither those nor the stale
							--                previous value (which would be 0x0A and fail the second).
							--   CDC FLAGS 32 selects AR=0x0F and does TWO data-port reads; the first
							--                takes STAT3 and leaves AR=0x10, so the second lands here,
							--                and it requires bit 5 of the result to be SET.
							-- 0xFF is the only value satisfying both.
							DO <= x"FF";
						end if;
						-- Only a DATA-PORT access auto-increments.  Reading FF8005 (RS=0) returns the
						-- address register itself and must leave it alone -- this increment used to sit
						-- outside the RS branch, so reading AR bumped AR.  mcd-verificator CDC REGS
						-- sub-test 08 walks AR 1..0x1F reading FF8005 at every step to check it, so a
						-- read that self-increments corrupts the very thing being measured.  (The write
						-- path below already scoped this correctly.)
						if AR /= "00000" then
							AR <= std_logic_vector( unsigned(AR) + 1 );
						end if;
					end if;
				end if;
			end if;
		end if;
	end process;
	
	
	process( RESET_N, CLK )
	variable CD_BYTE : std_logic_vector(7 downto 0);
	begin
		if RESET_N = '0' then
			PT <= (others => '0');
			WA <= (others => '0');
			IFSTAT(DECI) <= '1';
			STAT3(VALST) <= '1';
			HEAD0 <= (others => '0');
			HEAD1 <= (others => '0');
			HEAD2 <= (others => '0');
			HEAD3 <= x"01";
			
			CD_WR_OLD <= '0';
			WORD_CNT <= (others => '0');
			SECTOR_ACTIVE <= '0';
			RAM_POS <= (others => '0');
			DEC_POS <= (others => '0');
			DEC_DAT <= (others => '0');
			DEC_WR <= '0';
			DEC_WR_EN <= '0';
			DEC_HEAD01 <= (others => '0');
			DEC_HEAD23 <= (others => '0');
			SECTOR_END <= '0';
			
--			DECI_SET <= '0';
--			DECI_WAIT_CNT <= (others => '0');
		elsif rising_edge(CLK) then
			DEC_WR <= '0';
			SECTOR_END <= '0';
			-- frame timer: decoder interrupt without drive data (sync insertion), flag release, decoder off
			--
			-- Sync insertion stands in for a sector that did not arrive, so it must not pre-empt one
			-- that is arriving.  It was doing exactly that on every single frame: SECTOR_END restarts
			-- FRAME_CNT, and the frame timer is 715909 CLK = 13.333333 ms (exactly 75.000000 Hz) while
			-- the drive hands over a sector every 166667 ticks of the 12.5 MHz enable = 13.333360 ms
			-- and then takes ~200 us to stream 2352 bytes.  So DEC_FRAME always fired first, and
			-- because HEAD0..3 are only latched at the last word of the burst below, the sub CPU was
			-- woken to read a header that did not exist yet - it got the previous sector's, or a torn
			-- pair.  mcd-verificator's CDC INIT sub-test 03 has exactly one chance to catch LBA 0's
			-- header, which is why it failed intermittently.
			--
			-- SECTOR_ACTIVE is set between a sector's first and last word, so gating on it says
			-- "a sector is being decoded, do not insert a sync".  With no disc nothing streams, it
			-- stays low, and the free-running 75 Hz interrupt continues as before.  (It is a flag
			-- rather than "WORD_CNT /= 0" so this path is one flip-flop, not an 11-bit compare
			-- feeding DECI -> CDC_INT_N -> the ASIC's INT_PEND(5) on the 53.7 MHz clock.)
			-- The guard must expire.  A sector that stops part-way - CD-DA paused off a 1176-word
			-- boundary, a data burst cut short by the drive stopping - would otherwise leave
			-- SECTOR_ACTIVE set for ever and sync insertion would never fire again, which is the
			-- opposite of what it is for: software waiting on DECI would wait for ever.  Real
			-- silicon has no such latch; its frame counter free-runs, so any "a sector is coming"
			-- condition expires within a frame.  Clearing on DEC_FRAME bounds this one the same
			-- way: it can suppress at most one insertion, and a stalled stream self-heals on the
			-- next frame.  A word arriving in the same cycle wins, because the WORD_CNT block
			-- below assigns SECTOR_ACTIVE later in this process.
			if CTRL0(DECEN) = '0' then
				IFSTAT(DECI) <= '1';
				STAT3(VALST) <= '1';
			elsif DEC_FRAME = '1' and CTRL1(SYIEN) = '1' and SECTOR_ACTIVE = '0' then
				IFSTAT(DECI) <= '0';
				STAT3(VALST) <= '0';
			elsif DEC_MID = '1' then
				IFSTAT(DECI) <= '1';
				STAT3(VALST) <= '1';
			end if;
			if DEC_FRAME = '1' then
				SECTOR_ACTIVE <= '0';   -- the guard lasts one frame, never longer
			end if;
			if EN = '1' then
				if REG_WR = '1' then
					case ARD is
						when x"8" =>			--R8 WAL
							WA(7 downto 0) <= DI;
						when x"9" =>			--R9 WAH
							WA(15 downto 8) <= DI;
						when x"C" =>			--R12 PTL
							PT(7 downto 0) <= DI;
						when x"D" =>			--R13 PTH
							PT(15 downto 8) <= DI;
						when x"F" =>			--R15 RESET
							IFSTAT(DECI) <= '1';
							STAT3(VALST) <= '1';
						when others => null;
					end case;
				elsif REG_RD = '1' then
					case ARD is
						when x"F" =>			--R15 STAT3
							IFSTAT(DECI) <= '1';
							STAT3(VALST) <= '1';
						when others => null;
					end case;
				end if;
				
				DEC_WR_EN <= CTRL0(WRRQ);
			
				if CTRL0(DECEN) = '1' then
					CD_WR_OLD <= CD_WR;
					if CD_WR = '1' and CD_WR_OLD = '0' then
						DEC_DAT <= CD_DI;
						DEC_POS <= RAM_POS;

						-- a word of a sector is being taken: hold off sync insertion until the last one
						SECTOR_ACTIVE <= '1';
						if WORD_CNT = 2352/2-1 then
							SECTOR_ACTIVE <= '0';
						end if;

						WORD_CNT <= WORD_CNT + 1;
						if WORD_CNT = 0 then
--							DEC_WR_EN <= CTRL0(WRRQ);
						elsif WORD_CNT = 12/2 then
							DEC_HEAD01 <= CD_DI;
							if CTRL0(WRRQ) = '0' then
								HEAD0 <= CD_DI(7 downto 0);
								HEAD1 <= CD_DI(15 downto 8);
							end if;
							DEC_WR <= '1';
							RAM_POS <= RAM_POS + 2;
						elsif WORD_CNT = 14/2 then
							DEC_HEAD23 <= CD_DI;
							if CTRL0(WRRQ) = '0' then
								HEAD2 <= CD_DI(7 downto 0);
								HEAD3 <= CD_DI(15 downto 8);
							end if;
							DEC_WR <= '1';
							RAM_POS <= RAM_POS + 2;
						elsif WORD_CNT >= 16/2 and WORD_CNT <= (16+2048)/2-1 then
							DEC_WR <= '1';
							RAM_POS <= RAM_POS + 2;
						elsif WORD_CNT = 2352/2-1 then
--							DECI_SET <= '1';
							IFSTAT(DECI) <= '0';
							STAT3(VALST) <= '0';
							SECTOR_END <= '1';
						end if;
						
						if WORD_CNT = 2352/2-1 then
							WORD_CNT <= (others => '0');
							RAM_POS <= (others => '0');
--							DEC_WR_EN <= CTRL0(WRRQ);
						end if;
--						if CTRL0(WRRQ) = '0' then
--							DEC_WR_EN <= '0';
--						end if;

						if DEC_WR_EN = '1' then
----							WA <= std_logic_vector( unsigned(WA) + 2 );
							if WORD_CNT = 2352/2-1 then
								WA <= std_logic_vector( unsigned(WA) + 2352 );
								PT <= std_logic_vector( unsigned(PT) + 2352 );
								HEAD0 <= DEC_HEAD01(7 downto 0);
								HEAD1 <= DEC_HEAD01(15 downto 8);
								HEAD2 <= DEC_HEAD23(7 downto 0);
								HEAD3 <= DEC_HEAD23(15 downto 8);
							end if;
						end if;
					end if;
				else
					WORD_CNT <= (others => '0');
					SECTOR_ACTIVE <= '0';   -- decoder off: nothing is streaming
					RAM_POS <= (others => '0');
				end if;
			end if;
		end if;
	end process;
	
	DEC_ADDR <= std_logic_vector( unsigned(PT) + 2352 + DEC_POS );
	RAM_A_WR <= DEC_ADDR(15 downto 1);
	RAM_DO <= DEC_DAT;
	-- The CLK frequency follows the console region (53.69 MHz NTSC, 53.20 MHz PAL); the CD side is region
	-- independent, so the frame length is chosen by PALSW to keep 75 Hz in both.
	-- The CD hardware clock is region independent (50 MHz Mega CD oscillator) while CLK follows the console
	-- region (53.69 / 53.20 MHz), so the 75 Hz frame length is chosen by PALSW.
	FRAME_END <= to_unsigned(709378, 20) when PALSW = '1' else to_unsigned(715908, 20);
	FRAME_MID <= to_unsigned(283751, 20) when PALSW = '1' else to_unsigned(286363, 20);
	-- 75 Hz decoder frame timer: 53693175 / 75 = 715909 clocks per frame; the sector stream from the
	-- drive (one sector per frame) resynchronises it, so real data and the free-running frame coincide.
	process( RESET_N, CLK )
	begin
		if RESET_N = '0' then
			FRAME_CNT <= (others => '0');
			DEC_FRAME <= '0';
			DEC_MID <= '0';
		elsif rising_edge(CLK) then
			DEC_FRAME <= '0';
			DEC_MID <= '0';
			if CTRL0(DECEN) = '0' or SECTOR_END = '1' then
				FRAME_CNT <= (others => '0');
			elsif FRAME_CNT = FRAME_END then
				FRAME_CNT <= (others => '0');
				DEC_FRAME <= '1';
			else
				FRAME_CNT <= FRAME_CNT + 1;
				if FRAME_CNT = FRAME_MID then
					DEC_MID <= '1';
				end if;
			end if;
		end if;
	end process;

	RAM_WE <= DEC_WR and DEC_WR_EN and CTRL0(DECEN);

	DBG_SECTOR_END <= SECTOR_END;
	DBG_DEC_FRAME  <= DEC_FRAME;
	DBG_DEC_MID    <= DEC_MID;

	process( RESET_N, CLK )
	begin
		if RESET_N = '0' then
--			OLD_HRD_N <= '1';
			DT_EN <= '0';
		elsif rising_edge(CLK) then
			if EN = '1' then
				DT_EN <= not DT_EN;
				if DT_EN = '1' then
--					OLD_HRD_N <= HRD_N;
				end if;
			end if;
		end if;
	end process;
	
--	HRD_R <= HRD_N and not OLD_HRD_N;
--	HRD_F <= not HRD_N and OLD_HRD_N;
	
	process( RESET_N, CLK )
	begin
		if RESET_N = '0' then
			DBC <= (others => '0');
			DAC <= (others => '0');
			TS <= TS_IDLE;
			IFSTAT(DTEN) <= '1';
			IFSTAT(DTEI) <= '1';
			IFSTAT(DTBSY) <= '1';
			DTEN_N <= '1';
			WAIT_N <= '0';
			FIFO_DATA0 <= (others => '0');
--			FIFO_DATA1 <= (others => '0');
--			FIFO_WR_POS <= '0';
--			FIFO_RD_POS <= '0';
			
		elsif rising_edge(CLK) then
			if EN = '1' then
				if REG_WR = '1' then
					case ARD is
						when x"2" =>			--R2 DBCL
							DBC(7 downto 0) <= DI;
						when x"3" =>			--R3 DBCH
							DBC(15 downto 8) <= DI;
						when x"4" =>			--R4 DACL
							DAC(7 downto 0) <= DI;
						when x"5" =>			--R5 DACH
							DAC(15 downto 8) <= DI;
						when x"6" =>			--R6 DTTRG
--							IFSTAT(DTBSY) <= '0';
--							IFSTAT(DTEI) <= '1';
--							DBC(15 downto 12) <= "0000";
						when x"7" =>			--R6 DTACK
							IFSTAT(DTEI) <= '1';
							DBC(15 downto 12) <= "0000";
						when x"F" =>			--R15 RESET
--							IFSTAT(DTEN) <= '1';
--							IFSTAT(DTEI) <= '1';
--							IFSTAT(DTBSY) <= '1';
						when others => null;
					end case;
				end if;
				
				
				if (REG_WR = '1' and ARD = x"F") or (REG_WR = '1' and ARD = x"1" and DI(DOUTEN) = '0') then
					IFSTAT(DTBSY) <= '1';
					IFSTAT(DTEN) <= '1';
					IFSTAT(DTEI) <= '1';
					DTEN_N <= '1';
					
--					FIFO_RD_POS <= '0';
					FIFO_DATA0(8) <= '0';
--					FIFO_DATA1(8) <= '0';
					TS <= TS_IDLE;
				elsif REG_WR = '1' and ARD = x"6" then
					if IFCTRL(DOUTEN) = '1' then
						IFSTAT(DTBSY) <= '0';
--						IFSTAT(DTEN) <= '0';
						DBC(15 downto 12) <= "0000";
						
--						FIFO_RD_POS <= '0';
						FIFO_DATA0(8) <= '0';
--						FIFO_DATA1(8) <= '0';
					end if;
--				elsif REG_WR = '1' and AR = x"7" then
--					IFSTAT(DTEI) <= '1';
--					DBC(15 downto 12) <= "0000";
				elsif IFCTRL(DOUTEN) = '1' and DT_EN = '1' then--
					case TS is
						when TS_IDLE =>
							if IFSTAT(DTBSY) = '0' then
								WAIT_N <= '1';
								TS <= TS_WAIT;
							end if;
							
						when TS_WAIT =>
--							if FIFO_DATA0(8) = '0' then
--								FIFO_WR_POS <= '0';
								TS <= TS_FIFO;--TS_RAM_READ;
--							elsif FIFO_DATA1(8) = '0' then
--								FIFO_WR_POS <= '1';
--								TS <= TS_RAM_READ;
--							elsif DBC(11 downto 0) = x"000" then--IFSTAT(DTEN) = '1'
--								TS <= TS_IDLE;
--							end if;
							
						when TS_RAM_READ =>
							TS <= TS_FIFO;
						
						when TS_FIFO =>
--							if FIFO_WR_POS = '0' then
								FIFO_DATA0 <= "1" & RAM_DI;
								if IFSTAT(DTEN) = '1' then
									IFSTAT(DTEN) <= '0';
									DTEN_N <= '0';
								end if;
--							else
--								FIFO_DATA1 <= "1" & RAM_DI;
--							end if;
							DAC <= std_logic_vector( unsigned(DAC) + 1 );
							TS <= TS_SEND_WAIT;
							
						when TS_SEND_WAIT =>
							if HRD_N = '0' then
								WAIT_N <= '0';
								TS <= TS_SEND;
							end if;
						
						when TS_SEND =>
							if HRD_N = '1' then
								WAIT_N <= '1';
								
								DBC(11 downto 0) <= std_logic_vector( unsigned(DBC(11 downto 0)) - 1 );
--								FIFO_RD_POS <= not FIFO_RD_POS;
--								if FIFO_RD_POS = '0' then
--									FIFO_DATA0(8) <= '0';
--								else
--									FIFO_DATA1(8) <= '0';
--								end if;
						
								if DBC(11 downto 0) = x"000" then
									IFSTAT(DTEN) <= '1';
									IFSTAT(DTBSY) <= '1';
									IFSTAT(DTEI) <= '0';
									DTEN_N <= '1';
									DBC(15 downto 12) <= "1111";
									TS <= TS_IDLE;
								else
									TS <= TS_WAIT;
								end if;
							end if;
							
						when others => null;
					end case;
				
--					if HRD_F = '1' then
--						WAIT_N <= '0';
--					elsif HRD_R = '1' then
--						DBC(11 downto 0) <= std_logic_vector( unsigned(DBC(11 downto 0)) - 1 );
--						FIFO_RD_POS <= not FIFO_RD_POS;
--						if FIFO_RD_POS = '0' then
--							FIFO_DATA0(8) <= '0';
--						else
--							FIFO_DATA1(8) <= '0';
--						end if;
--						if DBC(11 downto 0) = x"000" then
--							IFSTAT(DTEN) <= '1';
--							IFSTAT(DTBSY) <= '1';
--							IFSTAT(DTEI) <= '0';
--							DTEN_N <= '1';
----							FIFO_RD_POS <= '0';
----							FIFO_DATA0(8) <= '0';
----							FIFO_DATA1(8) <= '0';
--							DBC(15 downto 12) <= "1111";
--							TS <= TS_IDLE;
--						end if;
--						WAIT_N <= '1';
--					end if;
				end if;
			end if;
		end if;
	end process;
	
	HDO <= FIFO_DATA0(7 downto 0);-- when FIFO_RD_POS = '0' else FIFO_DATA1(7 downto 0);
	
	RAM_A_RD <= DAC;
	
	
	INT_N <= (IFSTAT(DTEI) or not IFCTRL(DTEIEN)) and (IFSTAT(DECI) or not IFCTRL(DECIEN));
	
end rtl;
	