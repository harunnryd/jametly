use audio_backend::{chunk, AudioFormat, PcmFrame};
use proptest::prelude::*;

fn bridge_format() -> AudioFormat {
    AudioFormat::bridge()
}

proptest! {
    #[test]
    fn chunking_preserves_total_duration(
        samples in 0usize..48_000,
        max_ms in 10u32..1_000,
    ) {
        let frame = PcmFrame::new(0, bridge_format(), vec![0i16; samples]);
        let total = frame.duration_ms();
        let chunks = chunk(&frame, max_ms);

        let summed: u64 = chunks.iter().map(|c| c.duration_ms()).sum();
        prop_assert_eq!(summed, total);
    }

    #[test]
    fn no_chunk_exceeds_the_maximum(
        samples in 0usize..48_000,
        max_ms in 10u32..1_000,
    ) {
        let frame = PcmFrame::new(0, bridge_format(), vec![0i16; samples]);
        for piece in chunk(&frame, max_ms) {
            prop_assert!(piece.duration_ms() <= u64::from(max_ms));
        }
    }

    #[test]
    fn chunking_preserves_every_sample_in_order(
        samples in prop::collection::vec(any::<i16>(), 0..4_000),
        max_ms in 10u32..200,
    ) {
        let frame = PcmFrame::new(0, bridge_format(), samples.clone());
        let rejoined: Vec<i16> = chunk(&frame, max_ms)
            .iter()
            .flat_map(|c| c.samples.iter().copied())
            .collect();
        prop_assert_eq!(rejoined, samples);
    }

    #[test]
    fn chunk_timestamps_advance_by_their_own_duration(
        samples in 1usize..24_000,
        max_ms in 10u32..200,
    ) {
        let frame = PcmFrame::new(1_000, bridge_format(), vec![0i16; samples]);
        let chunks = chunk(&frame, max_ms);

        let mut expected = 1_000u64;
        for piece in &chunks {
            prop_assert_eq!(piece.ts_ms, expected);
            expected += piece.duration_ms();
        }
    }

    #[test]
    fn duration_never_panics_for_any_sample_count(samples in 0usize..96_000) {
        let frame = PcmFrame::new(0, bridge_format(), vec![0i16; samples]);
        let _ = frame.duration_ms();
    }
}
