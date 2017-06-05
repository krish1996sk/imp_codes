/////////////////////////////////////////////////////////////////////////////////////////////
// ê¸°ë³¸ ì ê³µì½ëë ìì ìì í´ë ê´ê³ ììµëë¤. ë¨, ìì¶ë ¥ í¬ë§· ì£¼ì
// ìë íì¤ ìì¶ë ¥ ìì  íìì ì°¸ê³ íì¸ì.
// íì¤ ìë ¥ ìì 
// int a;
// float b, c;
// double d, e, f;
// char g;
// char var[256];
// long long AB;
// cin >> a;                            // int ë³ì 1ê° ìë ¥ë°ë ìì 
// cin >> b >> c;                       // float ë³ì 2ê° ìë ¥ë°ë ìì  
// cin >> d >> e >> f;                  // double ë³ì 3ê° ìë ¥ë°ë ìì 
// cin >> g;                            // char ë³ì 1ê° ìë ¥ë°ë ìì 
// cin >> var;                          // ë¬¸ìì´ 1ê° ìë ¥ë°ë ìì 
// cin >> AB;                           // long long ë³ì 1ê° ìë ¥ë°ë ìì 
/////////////////////////////////////////////////////////////////////////////////////////////
// íì¤ ì¶ë ¥ ìì 
// int a = 0;                            
// float b = 1.0, c = 2.0;               
// double d = 3.0, e = 0.0; f = 1.0;
// char g = 'b';
// char var[256] = "ABCDEFG";
// long long AB = 12345678901234567L;
// cout << a;                           // int ë³ì 1ê° ì¶ë ¥íë ìì 
// cout << b << " " << c;               // float ë³ì 2ê° ì¶ë ¥íë ìì 
// cout << d << " " << e << " " << f;   // double ë³ì 3ê° ì¶ë ¥íë ìì 
// cout << g;                           // char ë³ì 1ê° ì¶ë ¥íë ìì 
// cout << var;                         // ë¬¸ìì´ 1ê° ì¶ë ¥íë ìì 
// cout << AB;                          // long long ë³ì 1ê° ì¶ë ¥íë ìì 
/////////////////////////////////////////////////////////////////////////////////////////////

#include<iostream>

using namespace std;

int print_flag;
int test_case_global;

    

int find_rank (string str,int str_size,int arr_size,int* arr,int reqrank,int i_recur){

    cout<<"function begin ";
    for(int i=0;i<arr_size;i++){
        cout<<arr[i]<<" ";
    }
    cout<<endl;


    int rank=1;
    if(reqrank==rank){
        cout << "#" << test_case_global<<" ";
        for(int k=0;k<i_recur;k++){
            cout<< str[ arr[0] +k ];
        }
        cout<<endl;
        //cout<<" here";
        print_flag = 1;  
        return -1;
    }
        
    int char_num;
    const int temp_arr_size = 'z' - 'a' +1;
    int rank_move;
    int temp_arr[temp_arr_size] ;
    int temp_arr2d [temp_arr_size][arr_size +1] ;
    for(int i=0;i<temp_arr_size;i++){
        temp_arr[i] = 0;
        for(int j=0;j< (arr_size+1)  ;j++){
            temp_arr2d[i][j] = 0;
        }
    }
    
    if(i_recur <str_size){
        
        
        
        for(int j=0;j<arr_size;j++){
            char_num =arr[j] + i_recur;
            if(char_num<str_size){
                temp_arr2d[ str[char_num] - 'a' ][ temp_arr[ str[char_num] - 'a' ] ] = arr[j] ;
                temp_arr[ str[char_num] - 'a'] =  temp_arr[ str[char_num] - 'a' ] + 1;
                //cout<<str[char_num]<<" "<<arr[j]<<endl;
            }
          
        }
        
        rank_move = rank;
        int prev_rank = rank;
        for(int j=0;j<temp_arr_size;j++){
            if( temp_arr[j]==1 ){
                rank_move=rank_move+ (  str_size - temp_arr2d[j][0] - i_recur  ) ;
                if(reqrank<=rank_move){
                    print_flag = 1;
                    cout << "#" << test_case_global<<" ";
                    for(int k=0;k<(i_recur+reqrank-prev_rank  );k++){
                        cout<< str[  temp_arr2d[j][0]  +k ];
                    }
                    cout<<endl;
                    //cout<<" hefk ";
                    return -1;
                        
                }   
            }
            else if( temp_arr[j] >1 ){
               //cout<<(reqrank-prev_rank)<<" rank-prevrank"<<endl;
                int temp =  find_rank (str,str_size,temp_arr[j],temp_arr2d[j], (reqrank-prev_rank) ,i_recur+1) ;
                if(print_flag ==1){
                    return -1;
                }  
                rank_move = rank_move + temp;
                            
            }
            prev_rank = rank_move;
                
        }     
    }
    return rank_move;
        
}
    
int main(int argc, char** argv){
    int test_case;
    int T;
    /*
       ìëì freopen í¨ìë input.txt ë¥¼ read only íìì¼ë¡ ì° í,
       ìì¼ë¡ íì¤ ìë ¥(í¤ë³´ë) ëì  input.txt íì¼ë¡ë¶í° ì½ì´ì¤ê² ë¤ë ìë¯¸ì ì½ëìëë¤.
       //ì¬ë¬ë¶ì´ ìì±í ì½ëë¥¼ íì¤í¸ í  ë, í¸ìë¥¼ ìí´ì input.txtì ìë ¥ì ì ì¥í í,
       freopen í¨ìë¥¼ ì´ì©íë©´ ì´í cin ì ìíí  ë íì¤ ìë ¥ ëì  íì¼ë¡ë¶í° ìë ¥ì ë°ìì¬ ì ììµëë¤.
       ë°ë¼ì íì¤í¸ë¥¼ ìíí  ëìë ìë ì£¼ìì ì§ì°ê³  ì´ í¨ìë¥¼ ì¬ì©íìë ì¢ìµëë¤.
       freopen í¨ìë¥¼ ì¬ì©íê¸° ìí´ìë #include <cstdio>, í¹ì #include <stdio.h> ê° íìí©ëë¤.
       ë¨, ì±ì ì ìí´ ì½ëë¥¼ ì ì¶íì¤ ëìë ë°ëì freopen í¨ìë¥¼ ì§ì°ê±°ë ì£¼ì ì²ë¦¬ íìì¼ í©ëë¤.
    */
    //freopen("input.txt", "r", stdin);
    cin>>T;
    /*
       ì¬ë¬ ê°ì íì¤í¸ ì¼ì´ì¤ê° ì£¼ì´ì§ë¯ë¡, ê°ê°ì ì²ë¦¬í©ëë¤.
    */
    for(test_case = 1; test_case <= T; ++test_case)
    {
        test_case_global = test_case;
        
        int rank;
        cin>>rank;
        string str;
        cin>>str;
        int str_size = str.length();
        //cout<<str_size<<endl;
        int temp_arr_size = 'z' - 'a' +1;
        int temp_arr[temp_arr_size]  ;
        //int* temp_arr = new int [temp_arr_size];
        int arr_2d[temp_arr_size][str_size+2] ;
        for(int i=0;i<temp_arr_size;i++){
            temp_arr[i] = 0;
            for(int j=0;j< (str_size+2)  ;j++){
                arr_2d[i][j] = 0;
            }
        }
        for(int i=0;i<str_size;i++){
            int a = str[i] - 'a' ;
            temp_arr[a] = temp_arr[a]+1;
            arr_2d[a][temp_arr[a] -1 ]= i ;
        }
        //int rank2=rank;
        int run_rank=0 ;
        int prevrank = 0;
        
        for(int i=0;i<temp_arr_size;i++){
            //cout<<"entered ";
            if(temp_arr[i] == 1){
                run_rank= prevrank + str_size - arr_2d[i][0];
                //cout<<"d"<<run_rank<<"a"<<endl;
                if(rank <= run_rank){
                    cout << "#" << test_case_global<<" ";
                    for(int k=0 ; k<(rank-prevrank) ; k++){
                        cout<<str[ arr_2d[i][0] + k];
                    }
                    cout<<endl;
                    //cout<<" ffkg";
                    goto next_test;
    
                }
                    
            }
            else if(temp_arr[i] > 1){
                //cout<<(rank-prevrank)<<endl ;
                run_rank = run_rank + find_rank(str,str_size,temp_arr[i],arr_2d[i], (rank-prevrank) , 1);
                if(print_flag==1){
                    print_flag=0;
                    goto next_test;
                    
                }
            }
            
            
            prevrank = run_rank;
                        
    }
        cout<<"none"<<endl;
        
        /////////////////////////////////////////////////////////////////////////////////////////////
        /*
             ì´ ë¶ë¶ì ì¬ë¬ë¶ì ìê³ ë¦¬ì¦ êµ¬íì´ ë¤ì´ê°ëë¤.
         */
        /////////////////////////////////////////////////////////////////////////////////////////////


        // íì¤ì¶ë ¥(íë©´)ì¼ë¡ ëµìì ì¶ë ¥í©ëë¤.
        next_test:
            continue;
        
    }
    return 0;  //ì ìì¢ë£ì ë°ëì 0ì ë¦¬í´í´ì¼í©ëë¤.
}
    
    