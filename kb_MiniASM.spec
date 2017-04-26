/*
A KBase module: kb_MiniASM
A simple wrapper for MiniASM Assembler
https://github.com/lh3/miniasm
*/

module kb_MiniASM {

    /* The workspace object name of a PairedEndLibrary file, whether of the
       KBaseAssembly or KBaseFile type.
    */
    typedef string paired_end_lib;

    /* Input parameters for running MiniASM.
        string workspace_name - the name of the workspace from which to take
           input and store output.
        list<paired_end_lib> read_libraries - Illumina PairedEndLibrary files
            to assemble.
        string output_contigset_name - the name of the output contigset
    */
    typedef structure {
        int mink_arg;                  /*  (=20)  minimum k value (<=124) */
        int maxk_arg;                  /*  (=100)  maximum k value (<=124) */
        int step_arg;                  /*  (=20)  increment of k-mer of each iteration  */
    } kval_args_type;

    typedef structure {
        string               workspace_name;
        list<paired_end_lib> read_libraries;                /*  input reads  */
        string               output_contigset_name;         /*  name of output contigs */
        int                  min_contig_arg;                /*  (=200) minimum size of contig */
        kval_args_type       kval_args;
    } MiniASM_Params;
    
    /* Output parameters for MiniASM run.
        string report_name - the name of the KBaseReport.Report workspace
            object.
        string report_ref - the workspace reference of the report.
    */
    typedef structure {
        string report_name;
        string report_ref;
    } MiniASM_Output;
    
    /* Run MiniASM on paired end libraries */
    funcdef run_MiniASM(MiniASM_Params params) returns(MiniASM_Output output)
        authentication required;
};
