#include <cstdio>
#include <set>
#include <cstring>
#include <string>

using namespace std;

multiset<int> s1,s2;  //0<=|s1|-|s2|<=1
char s[55];

void gao() {
int a,b;
bool f1,f2;	
	if (s1.empty()) {
		puts("Wrong!");
		return;
	}
	if (s1.size()==s2.size()) {
		a=*s1.rbegin();
		b=*s2.begin();
		f1=a%2;
		f2=b%2;
		if (f1==f2) {
			printf("%.0lf\n",(a*1.+b)/2.);
		}
		else {
			printf("%.1lf\n",(a*1.+b)/2.);
		}
	}
	else {
		printf("%d\n",*s1.rbegin());
	}
}

void gao1(int x) { //add x
	if (s1.empty()) {
		s1.insert(x);
	}
	else if (s1.size()==s2.size()) {
		s2.insert(x);
		s1.insert(*s2.begin());
		s2.erase(s2.begin());
	}
	else {
		s1.insert(x);
		s2.insert(*s1.rbegin());
		s1.erase(s1.find(*s1.rbegin()));
	}
	gao();

}

void gao2(int x) {
multiset<int>::iterator t1=s1.find(x),t2=s2.find(x);
	if ((t1==s1.end()) && (t2==s2.end())) {
		puts("Wrong!");
		return;
	}
	if (s1.size()==s2.size()) {
		if (t2!=s2.end()) {
			s2.erase(t2);
		}
		else {
			s1.erase(t1);
			s1.insert(*s2.begin());
			s2.erase(s2.begin());
		}
	}
	else if (t1!=s1.end()) {
		s1.erase(t1);
	}
	else {
		s2.erase(t2);
		s2.insert(*s1.rbegin());
		s1.erase(s1.find(*s1.rbegin()));
	}
	gao();
}

int main() {
int i,x;

	/*s1.clear();
	s2.clear();*/
	for (scanf("%d",&i);i;--i) {
		scanf("%s%d",s,&x);
		if (s[0]=='a') {
			gao1(x);
		}
		else {
			gao2(x);
		}
	}
	return 0;

}

